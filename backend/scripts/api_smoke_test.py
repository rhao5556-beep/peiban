import json
import httpx
import sys
import time

BASE = "http://127.0.0.1:8000/api/v1"


def get_token():
    r = httpx.post(f"{BASE}/auth/token", json={}, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data["access_token"]


def sse_post(message, headers, session_id=None):
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    with httpx.Client(timeout=20) as client:
        with client.stream(
            "POST",
            f"{BASE}/sse/message",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            resp.raise_for_status()
            sid = None
            events = []
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    raw = line[len("data:") :].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        continue
                    events.append(ev)
                    if ev.get("type") == "start":
                        sid = ev.get("session_id")
                    if ev.get("type") == "done":
                        break
            return sid, events


def sse_test(headers):
    with httpx.Client(timeout=10) as client:
        with client.stream(
            "GET",
            f"{BASE}/sse/test",
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            count = 0
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    count += 1
            return count


def main():
    try:
        token = get_token()
    except Exception as e:
        print("token failed:", str(e))
        return
    headers = {"Authorization": f"Bearer {token}"}

    try:
        d = httpx.get(f"{BASE}/affinity/dashboard", headers=headers, timeout=10)
        print("dashboard", d.status_code, bool(d.json()))
    except Exception as e:
        print("dashboard failed:", str(e))

    try:
        p = httpx.get(f"{BASE}/content/preference", headers=headers, timeout=10)
        pj = p.json() if p.status_code == 200 else {}
        print("preference", p.status_code, pj.get("content_recommendation_enabled"))
    except Exception as e:
        print("preference failed:", str(e))

    try:
        rec = httpx.get(f"{BASE}/content/recommendations", headers=headers, timeout=10)
        try:
            recs = rec.json()
        except Exception:
            recs = []
        count = len(recs) if isinstance(recs, list) else 0
        print("recommendations", rec.status_code, count)
        if rec.status_code == 200 and isinstance(recs, list) and recs:
            rid = recs[0].get("id")
            if rid:
                fb = httpx.post(
                    f"{BASE}/content/recommendations/{rid}/feedback",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"action": "liked"},
                    timeout=10,
                )
                print("feedback", fb.status_code, fb.json().get("success"))
    except Exception as e:
        print("recommendations failed:", str(e))

    try:
        cnt = sse_test(headers)
        print("sse_test events", cnt)
    except Exception as e:
        print("sse_test failed:", str(e))

    try:
        sid, ev = sse_post("你好", headers, None)
        print("sse_message sid", sid)
        print("sse_message types", [e.get("type") for e in ev if e.get("type") != "text"])
    except Exception as e:
        print("sse_message failed:", str(e))

    print("smoke test done")


if __name__ == "__main__":
    main()
