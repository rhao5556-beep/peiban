import argparse
import json
import os
import random
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parents[2] / "evals" / ".env.local"
    if _env_path.exists():
        load_dotenv(_env_path)
except Exception:
    pass


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sleep_backoff(attempt: int, cap_s: float) -> None:
    base = 1.5 ** attempt
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


_thread_local = threading.local()


def _get_thread_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


def _ask_backend(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    payload: Dict[str, Any],
    request_timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
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


def _get_memory_status(
    backend_base_url: str,
    access_token: str,
    memory_id: str,
    request_timeout_s: float,
) -> Optional[str]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/memories/{memory_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=float(request_timeout_s))
        if resp.status_code >= 500:
            return None
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("status") or "")
    except Exception:
        return None


def _iter_session_keys(conversation_obj: Dict[str, Any]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for k in conversation_obj.keys():
        if not k.startswith("session_"):
            continue
        if k.endswith("_date_time"):
            continue
        suffix = k.replace("session_", "")
        try:
            n = int(suffix)
        except Exception:
            continue
        if isinstance(conversation_obj.get(k), list):
            out.append((n, k))
    out.sort(key=lambda kv: kv[0])
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"))
    p.add_argument("--dataset_path", required=True)
    p.add_argument("--output_dir", default=str((Path("outputs") / "locomo_run").resolve()))
    p.add_argument("--mode", choices=["hybrid", "graph_only"], default="hybrid")
    p.add_argument("--eval_mode", action="store_true", default=True)
    p.add_argument("--user_id", default=None)
    p.add_argument("--limit_conversations", type=int, default=0)
    p.add_argument("--limit_questions", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--request_timeout_s", type=float, default=90.0)
    p.add_argument("--sleep_after_memorize_s", type=float, default=0.5)
    p.add_argument("--wait_memory_commit_s", type=float, default=120.0)
    p.add_argument("--chunk_size", type=int, default=64)
    args = p.parse_args()

    dataset = list(_load_json(Path(args.dataset_path)))
    if args.limit_conversations and args.limit_conversations > 0:
        dataset = dataset[: int(args.limit_conversations)]

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) / f"locomo10_{args.mode}_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    token_data = _get_token(args.backend_base_url, args.user_id)
    access_token = token_data["access_token"]
    user_id = token_data["user_id"]

    model_outputs: List[Dict[str, Any]] = []
    q_global_id = 1

    for conv_idx, conv in enumerate(dataset, start=1):
        conversation_obj = conv.get("conversation") or {}
        qa_list = list(conv.get("qa") or [])
        if args.limit_questions and args.limit_questions > 0:
            qa_list = qa_list[: int(args.limit_questions)]

        session_id: Optional[str] = None
        last_memory_id: Optional[str] = None

        session_keys = _iter_session_keys(conversation_obj)
        for session_n, session_key in session_keys:
            turns = list(conversation_obj.get(session_key) or [])
            for t in turns:
                speaker = str(t.get("speaker") or "").strip()
                text = str(t.get("text") or "").strip()
                dia_id = str(t.get("dia_id") or "").strip()
                if not speaker or not text:
                    continue

                msg = f"{speaker}: {text}"
                idempotency_key = f"locomo:mem:{user_id}:{conv_idx}:{session_n}:{dia_id}"
                payload: Dict[str, Any] = {
                    "message": msg,
                    "mode": args.mode,
                    "eval_mode": bool(args.eval_mode),
                    "remember": True,
                    "memorize_only": True,
                    "idempotency_key": idempotency_key,
                }
                if session_id:
                    payload["session_id"] = session_id

                session = _get_thread_session()
                resp = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    payload=payload,
                    request_timeout_s=args.request_timeout_s,
                )
                session_id = str(resp.get("session_id") or session_id or "")
                last_memory_id = str(resp.get("memory_id") or last_memory_id or "")

        if args.sleep_after_memorize_s and args.sleep_after_memorize_s > 0:
            time.sleep(float(args.sleep_after_memorize_s))

        if last_memory_id:
            deadline = time.time() + float(args.wait_memory_commit_s)
            while time.time() < deadline:
                st = _get_memory_status(
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    memory_id=last_memory_id,
                    request_timeout_s=args.request_timeout_s,
                )
                if st in {"committed", "pending_review"}:
                    break
                time.sleep(1.0)

        def _run_one(q_item: Dict[str, Any], local_idx: int) -> Dict[str, Any]:
            nonlocal session_id
            question = str(q_item.get("question") or "")
            reference_answer = str(q_item.get("answer") or "")
            evidence = q_item.get("evidence")
            category = q_item.get("category")

            idempotency_key = f"locomo:qa:{user_id}:{conv_idx}:{local_idx}"
            payload = {
                "message": question,
                "mode": args.mode,
                "eval_mode": bool(args.eval_mode),
                "remember": False,
                "memorize_only": False,
                "idempotency_key": idempotency_key,
            }
            if session_id:
                payload["session_id"] = session_id

            try:
                session = _get_thread_session()
                resp = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    payload=payload,
                    request_timeout_s=args.request_timeout_s,
                )
                reply = str(resp.get("reply") or "")
                cs = resp.get("context_source")
                sid = resp.get("session_id")
                turn_id = resp.get("turn_id")
                err = None
            except Exception as e:
                reply = ""
                cs = None
                sid = session_id
                turn_id = None
                err = f"{e.__class__.__name__}: {e}"

            return {
                "id": q_item.get("id") or 0,
                "task_type": f"locomo10_conv_{conv_idx}",
                "question": question,
                "reference_answer": reference_answer,
                "model_answer": reply,
                "meta": {
                    "category": category,
                    "evidence": evidence,
                    "affinity_base_url": args.backend_base_url,
                    "mode": args.mode,
                    "eval_mode": bool(args.eval_mode),
                    "user_id": user_id,
                    "session_id": sid,
                    "turn_id": turn_id,
                    "context_source": cs,
                    "error": err,
                },
            }

        for i, q in enumerate(qa_list, start=1):
            q["id"] = q_global_id
            q_global_id += 1

        outputs: List[Dict[str, Any]] = [None] * len(qa_list)  # type: ignore[list-item]
        total_n = len(qa_list)
        if total_n:
            with ThreadPoolExecutor(max_workers=max(1, int(args.concurrency))) as ex:
                fut_to_idx = {ex.submit(_run_one, q_item, idx): idx for idx, q_item in enumerate(qa_list, start=1)}
                pending = set(fut_to_idx.keys())
                done = 0
                last_heartbeat = time.time()
                while pending:
                    done_set, pending = wait(pending, timeout=15.0, return_when=FIRST_COMPLETED)
                    if not done_set:
                        now = time.time()
                        if now - last_heartbeat >= 15.0:
                            print(f"[conv {conv_idx}] [{done}/{total_n}] running...", flush=True)
                            last_heartbeat = now
                        continue
                    for fut in done_set:
                        idx = fut_to_idx[fut]
                        outputs[idx - 1] = fut.result()
                        done += 1
        model_outputs.extend(outputs if total_n else [])

    model_outputs_path = out_dir / f"locomo.locomo10.{run_ts}.model_outputs.json"
    model_outputs_path.write_text(json.dumps(model_outputs, ensure_ascii=False, indent=2), encoding="utf-8")

    run_summary = {
        "backend_base_url": args.backend_base_url,
        "mode": args.mode,
        "eval_mode": bool(args.eval_mode),
        "user_id": user_id,
        "timestamp": run_ts,
        "dataset_path": str(Path(args.dataset_path).resolve()),
        "limit_conversations": args.limit_conversations,
        "limit_questions": args.limit_questions,
        "sleep_after_memorize_s": args.sleep_after_memorize_s,
        "wait_memory_commit_s": args.wait_memory_commit_s,
        "output_file": str(model_outputs_path),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
