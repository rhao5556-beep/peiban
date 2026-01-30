import argparse
import json
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _row_to_line(r: Dict[str, Any]) -> str:
    rid = r.get("id")
    ts = r.get("timestamp")
    loc = r.get("location")
    action = r.get("action")
    dialogue = r.get("dialogue")
    env = r.get("environment")
    bg = r.get("background")
    inner = r.get("inner_thought")
    parts = []
    if action:
        parts.append(f"action: {action}")
    if dialogue:
        parts.append(f"dialogue: {dialogue}")
    if env:
        parts.append(f"environment: {env}")
    if bg:
        parts.append(f"background: {bg}")
    if inner:
        parts.append(f"inner_thought: {inner}")
    parts_joined = " | ".join(parts) if parts else ""
    return f"[id {rid}] {ts} @ {loc}: {parts_joined}".strip()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"))
    p.add_argument(
        "--dataset_path",
        default=str((Path(__file__).resolve().parents[2] / "external" / "KnowMeBench" / "KnowmeBench" / "dataset1" / "input" / "dataset1.json").resolve()),
    )
    p.add_argument("--user_id", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--sleep_s", type=float, default=0.05)
    p.add_argument("--request_timeout_s", type=float, default=60.0)
    args = p.parse_args()

    rows: List[Dict[str, Any]] = list(_load_json(Path(args.dataset_path)))
    if args.limit and args.limit > 0:
        rows = rows[: int(args.limit)]

    token_data = _get_token(args.backend_base_url, args.user_id)
    access_token = token_data["access_token"]
    user_id = token_data["user_id"]

    session_id: Optional[str] = None
    started = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, r in enumerate(rows, start=1):
        rid = r.get("id")
        msg = _row_to_line(r)
        ik = f"knowmebench:ingest:{user_id}:{rid}"
        payload: Dict[str, Any] = {
            "message": msg,
            "mode": "graph_only",
            "eval_mode": True,
            "retrieval_mode": "off",
            "remember": True,
            "memorize_only": True,
            "idempotency_key": ik,
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
        st = str(resp.get("memory_status") or "")
        mid = str(resp.get("memory_id") or "")
        if i <= 5 or i % 50 == 0 or i == len(rows):
            print(f"[{i}/{len(rows)}] memory_status={st} memory_id={mid}", flush=True)
        if args.sleep_s and args.sleep_s > 0:
            time.sleep(float(args.sleep_s))

    print(json.dumps({"started_at": started, "count": len(rows), "user_id": user_id, "session_id": session_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

