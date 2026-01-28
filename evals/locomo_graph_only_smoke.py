import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests


def _parse_session_ts(s: str) -> str:
    s = (s or "").strip()
    for fmt in ("%I:%M %p on %d %B, %Y", "%I:%M %p on %d %b, %Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(second=0).isoformat()
        except Exception:
            pass
    raise ValueError(f"unsupported session date format: {s!r}")


def _build_transcript(session_items, iso_ts: str) -> str:
    lines = []
    for item in session_items:
        dia_id = item.get("dia_id")
        speaker = item.get("speaker")
        text = item.get("text")
        if not dia_id or not speaker or not text:
            continue
        lines.append(f"[{dia_id} ts={iso_ts}] {speaker}: {text}")
    return "\n".join(lines)


def _call(req: requests.Session, method: str, url: str, **kw):
    last_exc = None
    for _ in range(5):
        try:
            return req.request(method, url, **kw)
        except Exception as e:
            last_exc = e
    raise last_exc


def main() -> int:
    backend = "http://localhost:8000"
    base = f"{backend}/api/v1"
    dataset_path = Path(__file__).resolve().parents[1] / "data" / "locomo" / "locomo10.json"

    req = requests.Session()
    _call(req, "GET", f"{backend}/health", timeout=20)
    tok = _call(req, "POST", f"{base}/auth/token", json={}, timeout=60).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    conv0 = data[0]["conversation"]
    iso_ts = _parse_session_ts(conv0["session_1_date_time"])
    transcript = _build_transcript(conv0["session_1"], iso_ts)

    sid = str(uuid.uuid4())
    r = _call(
        req,
        "POST",
        f"{base}/conversation/message",
        headers=headers,
        json={
            "message": transcript,
            "session_id": sid,
            "idempotency_key": str(uuid.uuid4()),
            "mode": "graph_only",
            "eval_mode": True,
        },
        timeout=120,
    )
    if r.status_code != 200:
        print("memorize_failed", r.status_code, r.text[:200])
        return 1

    qa = data[0]["qa"][:2]
    failures = 0
    for item in qa:
        q = item["question"]
        expected_raw = str(item["answer"])
        expected_norm = expected_raw
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                expected_norm = datetime.strptime(expected_raw, fmt).date().isoformat()
                break
            except Exception:
                pass
        prompt = (
            "Answer using only the facts from the earlier conversation transcript you memorized.\n"
            "Be specific. If unknown, say \"I don't know\".\n\n"
            f"Question: {q}\n"
            "Answer:"
        )
        a = _call(
            req,
            "POST",
            f"{base}/conversation/message",
            headers=headers,
            json={
                "message": prompt,
                "session_id": sid,
                "idempotency_key": str(uuid.uuid4()),
                "mode": "graph_only",
                "eval_mode": True,
            },
            timeout=120,
        ).json().get("reply", "")
        a_str = str(a)
        ok = (expected_raw in a_str) or (expected_norm in a_str)
        bad = "i don't know" in str(a).lower()
        print(json.dumps({"question": q, "expected": expected_raw, "expected_norm": expected_norm, "reply": a, "ok": ok, "dont_know": bad}, ensure_ascii=False))
        if (not ok) or bad:
            failures += 1

    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
