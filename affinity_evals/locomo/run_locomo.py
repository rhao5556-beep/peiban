import argparse
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


def _parse_session_dt(raw: str) -> Optional[datetime]:
    t = (raw or "").strip()
    if not t:
        return None
    fmts = [
        "%I:%M %p on %d %B, %Y",
        "%I:%M %p on %d %b, %Y",
        "%I:%M %p on %d %B %Y",
        "%I:%M %p on %d %b %Y",
    ]
    for f in fmts:
        try:
            return datetime.strptime(t, f)
        except Exception:
            continue
    return None


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    r = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _get_token(backend_base_url: str, user_id: Optional[str], timeout_s: float) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/auth/token"
    payload: Dict[str, Any] = {}
    if user_id:
        payload["user_id"] = user_id
    r = requests.post(url, json=payload, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _iter_dialogue_lines(conversation: Dict[str, Any]) -> Iterable[str]:
    keys: List[Tuple[int, str]] = []
    for k in conversation.keys():
        if k.startswith("session_") and k[len("session_") :].isdigit():
            keys.append((int(k[len("session_") :]), k))
    for _, k in sorted(keys, key=lambda x: x[0]):
        session_turns = conversation.get(k) or []
        raw_dt = str(conversation.get(f"{k}_date_time") or "").strip()
        dt = _parse_session_dt(raw_dt)
        dt_iso = dt.isoformat() if dt else ""
        for t in session_turns:
            if not isinstance(t, dict):
                continue
            speaker = str(t.get("speaker") or "").strip()
            text = str(t.get("text") or "").strip()
            if not text:
                continue
            blip = str(t.get("blip_caption") or "").strip()
            dia_id = str(t.get("dia_id") or "").strip()
            ts_part = f" ts={dt_iso}" if dt_iso else (f" ts={raw_dt}" if raw_dt else "")
            dia_part = f" {dia_id}" if dia_id else ""
            if speaker:
                line = f"[{dia_part.strip()}{ts_part}] {speaker}: {text}".strip()
            else:
                line = f"[{dia_part.strip()}{ts_part}] {text}".strip()
            if blip:
                line = f"{line} (image: {blip})"
            yield line


def _chunk_lines(lines: List[str], chunk_size: int) -> List[str]:
    if chunk_size <= 0:
        return ["\n".join(lines)]
    out: List[str] = []
    for i in range(0, len(lines), chunk_size):
        out.append("\n".join(lines[i : i + chunk_size]))
    return out


def _memorize_conversation(
    backend_base_url: str,
    access_token: str,
    session_id: str,
    lines: List[str],
    chunk_size: int,
    sleep_after_memorize_s: float,
    eval_mode: bool,
    mode: str,
    timeout_s: float,
) -> None:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    chunks = _chunk_lines(lines, chunk_size)
    for idx, chunk in enumerate(chunks, start=1):
        msg = chunk
        payload = {
            "message": msg,
            "session_id": session_id,
            "idempotency_key": f"locomo-mem-{session_id}-{idx}",
            "mode": mode,
            "eval_mode": bool(eval_mode),
        }
        _post_json(url, headers=headers, payload=payload, timeout_s=timeout_s)
        if sleep_after_memorize_s > 0:
            time.sleep(sleep_after_memorize_s)


def _ask_question(
    backend_base_url: str,
    access_token: str,
    session_id: str,
    question: str,
    mode: str,
    eval_mode: bool,
    timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    msg = (
        "Answer using only the facts from the earlier conversation transcript you memorized.\n"
        "Be specific. If unknown, say \"I don't know\".\n\n"
        f"Question: {question}\nAnswer:"
    )
    payload = {
        "message": msg,
        "session_id": session_id,
        "idempotency_key": f"locomo-q-{uuid.uuid4()}",
        "mode": mode,
        "eval_mode": bool(eval_mode),
    }
    return _post_json(url, headers=headers, payload=payload, timeout_s=timeout_s)


def _wait_outbox(
    backend_base_url: str,
    access_token: str,
    session_id: str,
    timeout_s: float,
    poll_interval_s: float,
    request_timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/evals/outbox/wait"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "session_id": session_id,
        "timeout_s": float(timeout_s),
        "poll_interval_ms": int(max(0.05, float(poll_interval_s)) * 1000),
    }
    r = requests.get(url, headers=headers, params=params, timeout=max(request_timeout_s, timeout_s + 5))
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", required=True)
    p.add_argument("--dataset_path", required=True)
    p.add_argument("--output_dir", required=True)
    p.add_argument("--mode", choices=["graph_only", "hybrid"], default="hybrid")
    p.add_argument("--eval_mode", action="store_true", default=False)
    p.add_argument("--user_id", default=None)
    p.add_argument("--limit_conversations", type=int, default=0)
    p.add_argument("--limit_questions", type=int, default=0)
    p.add_argument("--limit_turns", type=int, default=0)
    p.add_argument("--chunk_size", type=int, default=24)
    p.add_argument("--sleep_after_memorize_s", type=float, default=0.2)
    p.add_argument("--wait_outbox_timeout_s", type=float, default=60.0)
    p.add_argument("--wait_outbox_poll_interval_s", type=float, default=0.2)
    p.add_argument("--request_timeout_s", type=float, default=90.0)
    args = p.parse_args()

    dataset_path = Path(args.dataset_path)
    raw = _load_json(dataset_path)
    if not isinstance(raw, list):
        raise RuntimeError("dataset_path must be a JSON list")

    limit_convs = int(args.limit_conversations or 0)
    conversations = raw[:limit_convs] if limit_convs > 0 else raw

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(args.output_dir)
    out_dir = out_root / f"locomo10_{args.mode}_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    token = _get_token(args.backend_base_url, args.user_id, timeout_s=float(args.request_timeout_s))
    access_token = token["access_token"]
    user_id = token["user_id"]

    results: List[Dict[str, Any]] = []
    qid = 1

    for conv_idx, conv in enumerate(conversations):
        conv_id = f"conv-{conv_idx}"
        conv_obj = (conv or {}).get("conversation") or {}
        qa = (conv or {}).get("qa") or []

        session_id = str(uuid.uuid4())

        lines = list(_iter_dialogue_lines(conv_obj))
        if int(args.limit_turns or 0) > 0:
            lines = lines[: int(args.limit_turns)]

        if lines:
            _memorize_conversation(
                backend_base_url=args.backend_base_url,
                access_token=access_token,
                session_id=session_id,
                lines=lines,
                chunk_size=int(args.chunk_size),
                sleep_after_memorize_s=float(args.sleep_after_memorize_s),
                eval_mode=bool(args.eval_mode),
                mode=str(args.mode),
                timeout_s=float(args.request_timeout_s),
            )
            wait_timeout = float(args.wait_outbox_timeout_s or 0)
            if wait_timeout > 0:
                _wait_outbox(
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    session_id=session_id,
                    timeout_s=wait_timeout,
                    poll_interval_s=float(args.wait_outbox_poll_interval_s),
                    request_timeout_s=float(args.request_timeout_s),
                )

        limit_q = int(args.limit_questions or 0)
        qa_items = qa[:limit_q] if limit_q > 0 else qa
        for q in qa_items:
            if not isinstance(q, dict):
                continue
            question = str(q.get("question") or "")
            if not question:
                continue

            reference = q.get("answer", None)
            if reference is None:
                reference = q.get("reference_answer", None)

            resp = _ask_question(
                backend_base_url=args.backend_base_url,
                access_token=access_token,
                session_id=session_id,
                question=question,
                mode=args.mode,
                eval_mode=bool(args.eval_mode),
                timeout_s=float(args.request_timeout_s),
            )

            results.append(
                {
                    "id": qid,
                    "sample_id": conv_id,
                    "question": question,
                    "reference_answer": reference,
                    "model_answer": resp.get("reply"),
                    "evidence": q.get("evidence", []),
                    "category": q.get("category"),
                    "meta": {
                        "user_id": user_id,
                        "session_id": resp.get("session_id") or session_id,
                        "turn_id": resp.get("turn_id"),
                        "mode": args.mode,
                        "eval_mode": bool(args.eval_mode),
                        "context_source": resp.get("context_source"),
                    },
                }
            )
            qid += 1

    out_path = out_dir / f"locomo.locomo10.{run_ts}.model_outputs.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    run_summary = {
        "backend_base_url": args.backend_base_url,
        "mode": args.mode,
        "eval_mode": bool(args.eval_mode),
        "dataset_path": str(dataset_path),
        "output_dir": str(out_dir),
        "user_id": user_id,
        "total_items": len(results),
        "timestamp": run_ts,
    }
    (out_dir / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
