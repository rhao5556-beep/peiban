import httpx

BASE = "http://127.0.0.1:8000/api/v1"


def main():
    token = httpx.post(f"{BASE}/auth/token", json={}, timeout=30).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    recs = httpx.get(f"{BASE}/content/recommendations", headers=headers, timeout=30).json()
    print("recs", len(recs))
    if not recs:
        return

    chosen = None
    for r in recs:
        if r.get("tags"):
            chosen = r
            break
    if not chosen:
        chosen = recs[0]

    rid = chosen["id"]
    print("choose", chosen.get("title"), "tags", chosen.get("tags"))

    fb = httpx.post(
        f"{BASE}/content/recommendations/{rid}/feedback",
        headers={**headers, "Content-Type": "application/json"},
        json={"action": "liked"},
        timeout=30,
    )
    print("liked", fb.status_code, fb.text)

    pref = httpx.get(f"{BASE}/content/preference", headers=headers, timeout=30).json()
    print("preferred_sources", pref.get("preferred_sources"))
    print("excluded_topics", pref.get("excluded_topics"))


if __name__ == "__main__":
    main()
