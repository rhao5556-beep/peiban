import argparse
import json
import os
import random
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sleep_backoff(attempt: int, cap_s: float) -> None:
    base = 1.6 ** attempt
    jitter = random.random() * 0.5
    time.sleep(min(cap_s, base + jitter))


def _get_token(backend_base_url: str, user_id: Optional[str]) -> Dict[str, str]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/auth/token"
    payload = {"user_id": user_id} if user_id else {}
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt >= 5:
                break
            _sleep_backoff(attempt, cap_s=10.0)
    raise RuntimeError(f"failed_to_get_token: {last_error}")


def _ask_backend(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    message: str,
    mode: str,
    eval_mode: bool,
    session_id: str,
    request_timeout_s: float,
    memorize_only: bool,
    idempotency_key: str,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {
        "message": message,
        "mode": mode,
        "eval_mode": bool(eval_mode),
        "session_id": session_id,
        "memorize_only": bool(memorize_only),
        "idempotency_key": idempotency_key,
    }

    last_error: Exception | None = None
    for attempt in range(8):
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=float(request_timeout_s))
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt >= 7:
                break
            _sleep_backoff(attempt, cap_s=20.0)
    raise RuntimeError(f"backend_request_failed: {last_error}")


def _get_memory(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    memory_id: str,
    request_timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/memories/{memory_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = session.get(url, headers=headers, timeout=float(request_timeout_s))
    resp.raise_for_status()
    return resp.json()


def _wait_memory_committed(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    memory_id: str,
    timeout_s: float,
    request_timeout_s: float,
) -> bool:
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        try:
            mem = _get_memory(
                session=session,
                backend_base_url=backend_base_url,
                access_token=access_token,
                memory_id=memory_id,
                request_timeout_s=request_timeout_s,
            )
            if str(mem.get("status") or "") == "committed":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


_SESSION_KEY_RE = re.compile(r"^session_(\d+)$")
_DIA_ID_RE = re.compile(r"^(D\d+):(\d+)$")


def _iter_sessions(conv: Dict[str, Any]) -> List[Tuple[int, str, List[Dict[str, Any]]]]:
    out: List[Tuple[int, str, List[Dict[str, Any]]]] = []
    for k, v in (conv or {}).items():
        m = _SESSION_KEY_RE.match(k)
        if not m:
            continue
        idx = int(m.group(1))
        dt = str(conv.get(f"session_{idx}_date_time") or "")
        if isinstance(v, list):
            out.append((idx, dt, v))
    out.sort(key=lambda x: x[0])
    return out


def _format_utterance(u: Dict[str, Any]) -> str:
    speaker = str(u.get("speaker") or "").strip() or "speaker"
    text = str(u.get("text") or "").strip()
    parts = [f"{speaker}: {text}".strip()]
    blip = u.get("blip_caption")
    if blip:
        parts.append(f"(image: {str(blip).strip()})")
    return " ".join(p for p in parts if p).strip()


def _collect_required_dia_ids(qa: List[Dict[str, Any]], context_window: int) -> set[str]:
    ids: set[str] = set()
    for q in qa:
        ev = q.get("evidence") or []
        if isinstance(ev, list):
            for x in ev:
                if isinstance(x, str) and x:
                    ids.add(x.strip())

    if context_window <= 0:
        return ids

    expanded: set[str] = set(ids)
    for dia in list(ids):
        m = _DIA_ID_RE.match(dia)
        if not m:
            continue
        d = m.group(1)
        n = int(m.group(2))
        for k in range(max(1, n - context_window), n + context_window + 1):
            expanded.add(f"{d}:{k}")
    return expanded


def main() -> None:
    p = argparse.ArgumentParser(description="Run a lightweight LoCoMo10 pipeline against Affinity backend")
    p.add_argument("--backend_base_url", default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"))
    p.add_argument("--dataset_path", default=str(Path("data/locomo/locomo10.json").resolve()))
    p.add_argument("--output_dir", default=str(Path("outputs/locomo_run").resolve()))
    p.add_argument("--mode", choices=["hybrid", "graph_only"], default="hybrid")
    p.add_argument("--eval_mode", action="store_true", default=True)
    p.add_argument("--user_id", default=None)
    p.add_argument("--limit_conversations", type=int, default=0)
    p.add_argument("--limit_questions", type=int, default=0)
    p.add_argument("--sleep_after_memorize_s", type=float, default=0.3)
    p.add_argument("--request_timeout_s", type=float, default=120.0)
    p.add_argument("--memorize_only", action="store_true", default=True)
    p.add_argument("--evidence_only", action="store_true", default=True)
    p.add_argument("--evidence_context_window", type=int, default=0)
    p.add_argument("--wait_after_memorize_s", type=float, default=3.0)
    p.add_argument("--wait_for_commit_s", type=float, default=8.0)
    args = p.parse_args()

    dataset_path = Path(args.dataset_path)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    items = _load_json(dataset_path)
    if not isinstance(items, list):
        raise RuntimeError("dataset_path must be a JSON list")

    if args.limit_conversations and args.limit_conversations > 0:
        items = items[: int(args.limit_conversations)]

    token_data = _get_token(args.backend_base_url, args.user_id)
    access_token = token_data["access_token"]
    user_id = token_data["user_id"]

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_root / f"locomo10_{args.mode}_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    outputs: List[Dict[str, Any]] = []
    qid = 1
    mem_calls = 0

    for ci, conv_item in enumerate(items, start=1):
        conversation = conv_item.get("conversation") or {}
        qa = conv_item.get("qa") or []
        if not isinstance(qa, list):
            qa = []

        session_id = str(uuid.uuid4())

        q_iter = qa
        if args.limit_questions and args.limit_questions > 0:
            q_iter = qa[: int(args.limit_questions)]

        required_dia_ids: set[str] = set()
        if bool(args.evidence_only):
            required_dia_ids = _collect_required_dia_ids(q_iter, int(args.evidence_context_window))

        for _, dt, turns in _iter_sessions(conversation):
            if required_dia_ids:
                any_in_session = any(str(u.get("dia_id") or "") in required_dia_ids for u in turns)
                if not any_in_session:
                    continue
            if dt:
                mem_calls += 1
                r = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    message=f"[session_time] {dt}",
                    mode=args.mode,
                    eval_mode=bool(args.eval_mode),
                    session_id=session_id,
                    request_timeout_s=float(args.request_timeout_s),
                    memorize_only=bool(args.memorize_only),
                    idempotency_key=f"locomo_mem_{user_id}_{ci}_{mem_calls}",
                )
                mem_id = ((r.get("context_source") or {}).get("memory_id") if isinstance(r, dict) else None)
                if mem_id and args.wait_for_commit_s and args.wait_for_commit_s > 0:
                    _wait_memory_committed(
                        session=session,
                        backend_base_url=args.backend_base_url,
                        access_token=access_token,
                        memory_id=str(mem_id),
                        timeout_s=float(args.wait_for_commit_s),
                        request_timeout_s=float(args.request_timeout_s),
                    )
                if args.sleep_after_memorize_s and args.sleep_after_memorize_s > 0:
                    time.sleep(float(args.sleep_after_memorize_s))

            for u in turns:
                if required_dia_ids:
                    dia_id = str(u.get("dia_id") or "")
                    if dia_id not in required_dia_ids:
                        continue
                msg = _format_utterance(u)
                if not msg:
                    continue
                mem_calls += 1
                r = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    message=msg,
                    mode=args.mode,
                    eval_mode=bool(args.eval_mode),
                    session_id=session_id,
                    request_timeout_s=float(args.request_timeout_s),
                    memorize_only=bool(args.memorize_only),
                    idempotency_key=f"locomo_mem_{user_id}_{ci}_{mem_calls}",
                )
                mem_id = ((r.get("context_source") or {}).get("memory_id") if isinstance(r, dict) else None)
                if mem_id and args.wait_for_commit_s and args.wait_for_commit_s > 0:
                    _wait_memory_committed(
                        session=session,
                        backend_base_url=args.backend_base_url,
                        access_token=access_token,
                        memory_id=str(mem_id),
                        timeout_s=float(args.wait_for_commit_s),
                        request_timeout_s=float(args.request_timeout_s),
                    )
                if args.sleep_after_memorize_s and args.sleep_after_memorize_s > 0:
                    time.sleep(float(args.sleep_after_memorize_s))

                if mem_calls % 50 == 0:
                    print(f"[memorize] conv={ci}/{len(items)} calls={mem_calls}", flush=True)

        if args.wait_after_memorize_s and args.wait_after_memorize_s > 0:
            time.sleep(float(args.wait_after_memorize_s))

        for q in q_iter:
            question = str(q.get("question") or "")
            reference = q.get("answer")
            category = q.get("category")
            evidence = q.get("evidence") or []

            resp = _ask_backend(
                session=session,
                backend_base_url=args.backend_base_url,
                access_token=access_token,
                message=question,
                mode=args.mode,
                eval_mode=bool(args.eval_mode),
                session_id=session_id,
                request_timeout_s=float(args.request_timeout_s),
                memorize_only=False,
                idempotency_key=f"locomo_q_{user_id}_{ci}_{qid}",
            )

            outputs.append(
                {
                    "id": qid,
                    "task_type": "LoCoMo",
                    "question": question,
                    "reference_answer": reference,
                    "model_answer": resp.get("reply", ""),
                    "category": int(category) if isinstance(category, int) else None,
                    "meta": {
                        "backend_base_url": args.backend_base_url,
                        "mode": args.mode,
                        "eval_mode": bool(args.eval_mode),
                        "user_id": user_id,
                        "conversation_index": ci,
                        "session_id": session_id,
                        "evidence": evidence,
                        "context_source": resp.get("context_source"),
                        "turn_id": resp.get("turn_id"),
                    },
                }
            )
            qid += 1

    model_out_path = out_dir / f"locomo10.{args.mode}.{run_ts}.model_outputs.json"
    model_out_path.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")

    run_summary = {
        "backend_base_url": args.backend_base_url,
        "mode": args.mode,
        "eval_mode": bool(args.eval_mode),
        "user_id": user_id,
        "timestamp": run_ts,
        "limit_conversations": int(args.limit_conversations),
        "limit_questions": int(args.limit_questions),
        "sleep_after_memorize_s": float(args.sleep_after_memorize_s),
        "request_timeout_s": float(args.request_timeout_s),
        "total_questions": len(outputs),
        "model_outputs_path": str(model_out_path),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(out_dir))


if __name__ == "__main__":
    main()
