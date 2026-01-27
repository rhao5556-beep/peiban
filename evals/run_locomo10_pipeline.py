import argparse
import json
import time
import uuid
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_token(backend_base_url: str, user_id: Optional[str]) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/auth/token"
    payload: Dict[str, Any] = {}
    if user_id:
        payload["user_id"] = user_id
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def _sse_post_message(
    backend_base_url: str,
    access_token: str,
    message: str,
    session_id: str,
    mode: str,
    eval_mode: bool,
    observed_at: Optional[datetime] = None,
) -> Tuple[List[str], List[str]]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/sse/message"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "message": message,
        "session_id": session_id,
        "idempotency_key": str(uuid.uuid4()),
        "mode": mode,
        "eval_mode": bool(eval_mode),
        "memorize_only": True,
    }
    if observed_at:
        payload["observed_at"] = observed_at.isoformat()
    max_retries = 3
    for attempt in range(max_retries + 1):
        max_total_s = 120.0
        max_no_data_s = 45.0
        start = time.monotonic()
        last_data = start
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=(20, 30)) as r:
            if r.status_code == 429:
                retry_after = 60
                try:
                    retry_after = int(r.headers.get("Retry-After", "60"))
                except Exception:
                    retry_after = 60
                if attempt >= max_retries:
                    body = ""
                    try:
                        body = (r.text or "")[:2000]
                    except Exception:
                        body = ""
                    raise RuntimeError(f"sse_message_http_429: {body}")
                time.sleep(max(1, retry_after))
                continue
            if r.status_code >= 400:
                body = ""
                try:
                    body = (r.text or "")[:2000]
                except Exception:
                    body = ""
                raise RuntimeError(f"sse_message_http_{r.status_code}: {body}")
            event_ids = []
            memory_ids = []
            for raw in r.iter_lines(decode_unicode=True):
                now = time.monotonic()
                if now - start > max_total_s:
                    raise TimeoutError(f"sse_message_timeout_total_{max_total_s}s")
                if now - last_data > max_no_data_s:
                    raise TimeoutError(f"sse_message_timeout_no_data_{max_no_data_s}s")
                if not raw:
                    continue
                if raw.startswith("data:"):
                    last_data = now
                    data = raw[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        ev = json.loads(data)
                    except Exception:
                        continue
                    if ev.get("type") == "memory_pending":
                        mid = ev.get("memory_id")
                        if isinstance(mid, str) and mid:
                            memory_ids.append(mid)
                        meta = ev.get("metadata") or {}
                        eid = meta.get("event_id") if isinstance(meta, dict) else None
                        if isinstance(eid, str) and eid:
                            event_ids.append(eid)
                    if ev.get("type") in ("done", "error"):
                        break
            return event_ids, memory_ids
    raise RuntimeError("sse_message_retry_exhausted")


def _wait_outbox_done(event_ids: List[str], timeout_s: float) -> None:
    if not event_ids or timeout_s <= 0:
        return
    try:
        from app.core.config import settings
        from sqlalchemy import create_engine, text
    except Exception:
        return
    eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    params = {f"e{i}": eid for i, eid in enumerate(event_ids)}
    placeholders = ", ".join([f":e{i}" for i in range(len(event_ids))])
    q = text(f"SELECT COUNT(1) FROM outbox_events WHERE event_id IN ({placeholders}) AND status != 'done'")
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        try:
            with eng.connect() as c:
                remaining = c.execute(q, params).scalar() or 0
            if int(remaining) == 0:
                return
        except Exception:
            return
        time.sleep(1.0)


def _post_message(
    backend_base_url: str,
    access_token: str,
    message: str,
    session_id: str,
    mode: str,
    eval_mode: bool,
    request_timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {
        "message": message,
        "session_id": session_id,
        "mode": mode,
        "eval_mode": bool(eval_mode),
    }
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=float(request_timeout_s))
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} {r.text}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = e
            if attempt >= 5:
                break
            time.sleep(min(10.0, 0.5 * (2 ** attempt)))
    raise RuntimeError(f"backend_request_failed: {last_error}")


def _iter_conversation_turns(conv: Dict[str, Any]) -> List[str]:
    c = conv.get("conversation") or {}
    turns: List[str] = []
    for i in range(1, 60):
        sess_key = f"session_{i}"
        if sess_key not in c:
            continue
        items = c.get(sess_key) or []
        if isinstance(items, list):
            for it in items:
                t = (it or {}).get("text")
                if isinstance(t, str) and t.strip():
                    turns.append(t.strip())
    return turns


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _parse_session_datetime(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    s = text.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})$", s, flags=re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    ap = m.group(3).lower()
    day = int(m.group(4))
    mon_name = m.group(5).lower()
    year = int(m.group(6))
    mon = _MONTHS.get(mon_name)
    if not mon:
        return None
    if ap == "pm" and hour != 12:
        hour += 12
    if ap == "am" and hour == 12:
        hour = 0
    try:
        return datetime(year, mon, day, hour, minute, 0)
    except Exception:
        return None


def _iter_session_turns_with_time(conv: Dict[str, Any]) -> List[Tuple[str, Optional[datetime]]]:
    c = conv.get("conversation") or {}
    out: List[Tuple[str, Optional[datetime]]] = []
    for i in range(1, 60):
        sess_key = f"session_{i}"
        if sess_key not in c:
            continue
        base_dt = _parse_session_datetime(c.get(f"{sess_key}_date_time"))
        items = c.get(sess_key) or []
        if not isinstance(items, list):
            continue
        for j, it in enumerate(items):
            t = (it or {}).get("text")
            if isinstance(t, str) and t.strip():
                sp = (it or {}).get("speaker")
                if isinstance(sp, str) and sp.strip():
                    t = f"{sp.strip()}: {t.strip()}"
                else:
                    t = t.strip()
                dt = base_dt + timedelta(seconds=j * 15) if base_dt else None
                out.append((t, dt))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend_base_url", default="http://localhost:8000")
    parser.add_argument("--dataset_path", default="data/locomo/locomo10.json")
    parser.add_argument("--output_dir", default="outputs/locomo_run")
    parser.add_argument("--mode", choices=["graph_only", "hybrid"], default="hybrid")
    parser.add_argument("--eval_mode", action="store_true", default=True)
    parser.add_argument("--limit_conversations", type=int, default=0)
    parser.add_argument("--limit_questions", type=int, default=0)
    parser.add_argument("--limit_turns", type=int, default=0)
    parser.add_argument("--sleep_after_memorize_s", type=float, default=0.5)
    parser.add_argument("--wait_outbox_done_s", type=float, default=0.0)
    parser.add_argument("--request_timeout_s", type=float, default=180.0)
    parser.add_argument("--user_id", default=None)
    args = parser.parse_args()

    dataset_path = Path(args.dataset_path)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_root / f"locomo10_{args.mode}_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    token_data = _get_token(args.backend_base_url, args.user_id)
    access_token = token_data["access_token"]
    user_id = token_data["user_id"]

    dataset = _load_json(dataset_path)
    if not isinstance(dataset, list):
        raise RuntimeError("invalid_dataset_format")

    conv_iter = dataset
    if args.limit_conversations and args.limit_conversations > 0:
        conv_iter = dataset[: args.limit_conversations]

    model_outputs: List[Dict[str, Any]] = []
    run_summary = {
        "backend_base_url": args.backend_base_url,
        "dataset_path": str(dataset_path.resolve()),
        "mode": args.mode,
        "eval_mode": bool(args.eval_mode),
        "timestamp": run_ts,
        "conversations": [],
    }

    for idx, conv in enumerate(conv_iter):
        session_id = str(uuid.uuid4())
        turns_with_time = _iter_session_turns_with_time(conv)
        if not turns_with_time:
            turns_with_time = [(t, None) for t in _iter_conversation_turns(conv)]
        if args.limit_turns and args.limit_turns > 0:
            turns_with_time = turns_with_time[: args.limit_turns]
        total_convs = len(conv_iter)
        print(f"[locomo] conversation {idx + 1}/{total_convs}: memorizing {len(turns_with_time)} turns")
        all_event_ids: List[str] = []
        for j, (t, dt) in enumerate(turns_with_time):
            event_ids, _ = _sse_post_message(
                backend_base_url=args.backend_base_url,
                access_token=access_token,
                message=t,
                session_id=session_id,
                mode=args.mode,
                eval_mode=bool(args.eval_mode),
                observed_at=dt,
            )
            all_event_ids.extend(event_ids)
            if (j + 1) % 10 == 0 or (j + 1) == len(turns_with_time):
                print(f"[locomo] memorized {j + 1}/{len(turns_with_time)}")
        _wait_outbox_done(all_event_ids, float(args.wait_outbox_done_s))
        if args.sleep_after_memorize_s and args.sleep_after_memorize_s > 0:
            time.sleep(float(args.sleep_after_memorize_s))

        qa = conv.get("qa") or []
        if not isinstance(qa, list):
            qa = []
        qa_iter = qa
        if args.limit_questions and args.limit_questions > 0:
            qa_iter = qa[: args.limit_questions]
        print(f"[locomo] conversation {idx + 1}/{total_convs}: answering {len(qa_iter)} questions")

        for k, q in enumerate(qa_iter):
            question = (q or {}).get("question")
            answer = (q or {}).get("answer")
            evidence = (q or {}).get("evidence")
            category = (q or {}).get("category")
            if not isinstance(question, str):
                continue
            resp = _post_message(
                backend_base_url=args.backend_base_url,
                access_token=access_token,
                message=question,
                session_id=session_id,
                mode=args.mode,
                eval_mode=bool(args.eval_mode),
                request_timeout_s=float(args.request_timeout_s),
            )
            model_outputs.append(
                {
                    "id": len(model_outputs) + 1,
                    "sample_id": f"conv-{idx}",
                    "question": question,
                    "reference_answer": answer,
                    "model_answer": resp.get("reply", ""),
                    "evidence": evidence,
                    "category": category,
                    "meta": {
                        "user_id": user_id,
                        "session_id": resp.get("session_id", session_id),
                        "turn_id": resp.get("turn_id"),
                        "mode": args.mode,
                        "eval_mode": bool(args.eval_mode),
                        "context_source": resp.get("context_source"),
                    },
                }
            )
            if (k + 1) % 5 == 0 or (k + 1) == len(qa_iter):
                print(f"[locomo] answered {k + 1}/{len(qa_iter)}")

        run_summary["conversations"].append(
            {
                "sample_id": f"conv-{idx}",
                "user_id": user_id,
                "session_id": session_id,
                "transcript_turns": len(turns_with_time),
                "memorized": len(turns_with_time),
                "questions": len(qa_iter),
            }
        )

    out_model = out_dir / f"locomo.locomo10.{run_ts}.model_outputs.json"
    out_run = out_dir / f"locomo.locomo10.{run_ts}.run_summary.json"
    out_model.write_text(json.dumps(model_outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    out_run.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(out_dir.resolve()))


if __name__ == "__main__":
    main()
