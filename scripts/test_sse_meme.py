import json
import time
import urllib.request


def main():
    base = "http://localhost:8000"

    token_req = urllib.request.Request(
        f"{base}/api/v1/auth/token",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(token_req, timeout=10) as resp:
        token = json.load(resp)["access_token"]

    body = json.dumps({"message": "讲个开心的事情吧"}).encode("utf-8")
    sse_req = urllib.request.Request(
        f"{base}/api/v1/sse/message",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )

    start = time.time()
    with urllib.request.urlopen(sse_req, timeout=30) as res:
        for raw in res:
            line = raw.decode("utf-8", "ignore").strip()
            if not line or not line.startswith("data:"):
                continue
            evt = json.loads(line[5:].strip())
            print(evt.get("type"), evt.get("metadata"))
            if evt.get("type") == "meme":
                break
            if time.time() - start > 20:
                break


if __name__ == "__main__":
    main()

