def normalize_openai_base_url(base_url: str) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        return base_url
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"

