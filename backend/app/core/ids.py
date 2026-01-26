import uuid


def normalize_uuid(value: str) -> str:
    raw = str(value)
    try:
        return str(uuid.UUID(raw))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))

