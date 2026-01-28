import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def _sleep_backoff(attempt: int, cap_s: float) -> None:
    base = 1.5**attempt
    jitter = (attempt + 1) * 0.1
    time.sleep(min(cap_s, base + jitter))


def _parse_session_ts(s: str) -> str:
    s = (s or "").strip()
    for fmt in ("%I:%M %p on %d %B, %Y", "%I:%M %p on %d %b, %Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(second=0).isoformat()
        except Exception:
            pass
    raise ValueError(f"unsupported session date format: {s!r}")


def _iter_sessions(conv: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    sessions: List[Tuple[str, List[Dict[str, Any]]]] = []
    for k, v in conv.items():
        if not k.startswith("session_") or not k.endswith("_date_time"):
            continue
        prefix = k[: -len("_date_time")]
        session_rows = conv.get(prefix)
        if isinstance(session_rows, list) and isinstance(v, str):
            sessions.append((v, session_rows))
    def _key(x: Tuple[str, List[Dict[str, Any]]]) -> datetime:
        return datetime.fromisoformat(_parse_session_ts(x[0]))
    sessions.sort(key=_key)
    return sessions


def _sessions_by_number(conv: Dict[str, Any]) -> Dict[int, Tuple[str, List[Dict[str, Any]]]]:
    out: Dict[int, Tuple[str, List[Dict[str, Any]]]] = {}
    for k, v in conv.items():
        if not k.startswith("session_") or not k.endswith("_date_time"):
            continue
        num_s = k[len("session_") : -len("_date_time")]
        try:
            n = int(num_s)
        except Exception:
            continue
        rows = conv.get(f"session_{n}")
        if isinstance(v, str) and isinstance(rows, list):
            out[n] = (v, rows)
    return out


def _build_transcript(session_items: List[Dict[str, Any]], iso_ts: str) -> str:
    lines: List[str] = []
    for item in session_items:
        dia_id = item.get("dia_id")
        speaker = item.get("speaker")
        text = item.get("text")
        if not dia_id or not speaker or not text:
            continue
        lines.append(f"[{dia_id} ts={iso_ts}] {speaker}: {text}")
    return "\n".join(lines)


def _chunk_lines(s: str, chunk_size: int) -> List[str]:
    lines = [ln for ln in (s or "").splitlines() if ln.strip()]
    if chunk_size <= 0:
        return ["\n".join(lines)] if lines else [""]
    out: List[str] = []
    for i in range(0, len(lines), chunk_size):
        out.append("\n".join(lines[i : i + chunk_size]))
    return out if out else [""]


def _get_token(backend_base_url: str, user_id: Optional[str]) -> Dict[str, str]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/auth/token"
    payload = {"user_id": user_id} if user_id else {}
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            resp = requests.post(url, json=payload, timeout=20)
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
    session_id: Optional[str],
    request_timeout_s: float,
    idempotency_key: Optional[str],
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {"message": message, "mode": mode, "eval_mode": bool(eval_mode)}
    if session_id:
        payload["session_id"] = session_id
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key

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


@dataclass(frozen=True)
class ModelOutput:
    id: int
    sample_id: str
    question: str
    reference_answer: Any
    model_answer: str
    evidence: Any
    category: Optional[int]
    meta: Dict[str, Any]


def _normalize_reference_answer(ans: Any) -> Any:
    if isinstance(ans, (int, float, bool)) or ans is None:
        return ans
    if isinstance(ans, str):
        return ans
    return str(ans)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"))
    p.add_argument("--dataset_path", required=True)
    p.add_argument("--output_dir", required=True)
    p.add_argument("--mode", choices=["hybrid", "graph_only"], default="hybrid")
    p.add_argument("--eval_mode", action="store_true", default=False)
    p.add_argument("--limit_conversations", type=int, default=0)
    p.add_argument("--limit_questions", type=int, default=0)
    p.add_argument("--chunk_size", type=int, default=64)
    p.add_argument("--sleep_after_memorize_s", type=float, default=0.5)
    p.add_argument("--user_id", default=None)
    p.add_argument("--request_timeout_s", type=float, default=120.0)
    args = p.parse_args()

    dataset = json.loads(Path(args.dataset_path).read_text(encoding="utf-8"))
    if not isinstance(dataset, list):
        raise RuntimeError("dataset_path must contain a JSON list")

    token_data = _get_token(args.backend_base_url, args.user_id)
    access_token = token_data["access_token"]
    user_id = token_data.get("user_id") or args.user_id

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) / f"locomo10_{args.mode}_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(
        f"run_locomo: mode={args.mode} eval_mode={bool(args.eval_mode)} "
        f"limit_conversations={int(args.limit_conversations)} limit_questions={int(args.limit_questions)}",
        file=sys.stderr,
        flush=True,
    )

    outputs: List[ModelOutput] = []
    next_id = 1

    conv_iter = dataset
    if args.limit_conversations and args.limit_conversations > 0:
        conv_iter = dataset[: args.limit_conversations]

    req = requests.Session()

    for conv_idx, row in enumerate(conv_iter):
        conv = row.get("conversation") if isinstance(row, dict) else None
        qa = row.get("qa") if isinstance(row, dict) else None
        if not isinstance(conv, dict) or not isinstance(qa, list):
            continue

        session_id = str(uuid.uuid4())
        idempotency_prefix = str(uuid.uuid4())
        print(f"[conv {conv_idx}] memorize start", file=sys.stderr, flush=True)

        q_iter = qa
        if args.limit_questions and args.limit_questions > 0:
            q_iter = qa[: args.limit_questions]

        needed_sessions: set[int] = set()
        for q in q_iter:
            if not isinstance(q, dict):
                continue
            ev = q.get("evidence")
            if isinstance(ev, list):
                for e in ev:
                    if isinstance(e, str) and e.startswith("D") and ":" in e:
                        try:
                            needed_sessions.add(int(e[1:].split(":", 1)[0]))
                        except Exception:
                            pass

        sessions_map = _sessions_by_number(conv)
        if needed_sessions:
            session_nums = [n for n in sorted(needed_sessions) if n in sessions_map]
        else:
            session_nums = sorted(sessions_map.keys())

        for sess_idx, n in enumerate(session_nums):
            sess_dt, sess_items = sessions_map[n]
            iso_ts = _parse_session_ts(sess_dt)
            transcript = _build_transcript(sess_items, iso_ts)
            for chunk_i, chunk in enumerate(_chunk_lines(transcript, int(args.chunk_size))):
                if not chunk.strip():
                    continue
                _ask_backend(
                    req,
                    args.backend_base_url,
                    access_token,
                    chunk,
                    args.mode,
                    bool(args.eval_mode),
                    session_id,
                    float(args.request_timeout_s),
                    idempotency_key=f"{idempotency_prefix}:s{sess_idx}:c{chunk_i}",
                )
                if args.sleep_after_memorize_s and args.sleep_after_memorize_s > 0:
                    time.sleep(float(args.sleep_after_memorize_s))
            print(f"[conv {conv_idx}] session {n} memorized", file=sys.stderr, flush=True)

        for q in q_iter:
            if not isinstance(q, dict) or "question" not in q:
                continue
            question = str(q.get("question", ""))
            reference_answer = _normalize_reference_answer(q.get("answer"))
            evidence = q.get("evidence")
            category = q.get("category")
            payload = (
                "Answer using only the facts from the earlier conversation transcript you memorized.\n"
                "Be specific. If unknown, say \"I don't know\".\n\n"
                f"Question: {question}\n"
                "Answer:"
            )

            resp = _ask_backend(
                req,
                args.backend_base_url,
                access_token,
                payload,
                args.mode,
                bool(args.eval_mode),
                session_id,
                float(args.request_timeout_s),
                idempotency_key=f"{idempotency_prefix}:q{next_id}",
            )
            model_answer = str(resp.get("reply", ""))
            meta = {
                "user_id": user_id,
                "session_id": session_id,
                "turn_id": resp.get("turn_id"),
                "mode": args.mode,
                "eval_mode": bool(args.eval_mode),
                "context_source": resp.get("context_source"),
            }
            outputs.append(
                ModelOutput(
                    id=next_id,
                    sample_id=f"conv-{conv_idx}",
                    question=question,
                    reference_answer=reference_answer,
                    model_answer=model_answer,
                    evidence=evidence,
                    category=category if isinstance(category, int) else None,
                    meta=meta,
                )
            )
            next_id += 1
            if next_id <= 6 or next_id % 10 == 0:
                elapsed_s = time.time() - t0
                print(
                    f"[q {next_id - 1}] ok elapsed={elapsed_s:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )

    model_outputs_path = out_dir / f"locomo.locomo10.{run_ts}.model_outputs.json"
    model_outputs_path.write_text(
        json.dumps([asdict(x) for x in outputs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    run_summary = {
        "backend_base_url": args.backend_base_url,
        "dataset_path": str(Path(args.dataset_path).resolve()),
        "mode": args.mode,
        "eval_mode": bool(args.eval_mode),
        "timestamp": run_ts,
        "limit_conversations": int(args.limit_conversations),
        "limit_questions": int(args.limit_questions),
        "chunk_size": int(args.chunk_size),
        "sleep_after_memorize_s": float(args.sleep_after_memorize_s),
        "total_items": len(outputs),
        "output_file": str(model_outputs_path),
    }
    (out_dir / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
