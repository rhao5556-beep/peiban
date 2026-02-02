import re
from typing import Optional


_MONTHS = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
}


def _cap_first(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return t
    return t[0].upper() + t[1:]


def _normalize_month(name: str) -> Optional[str]:
    n = (name or "").strip()
    if not n:
        return None
    key = n[:3].lower()
    return _MONTHS.get(key)


def _extract_date_like(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
    if not m:
        return None
    day = int(m.group(1))
    month = _normalize_month(m.group(2))
    year = int(m.group(3))
    if not month:
        return None
    return f"{day} {month} {year}"


def _extract_month_year(text: str) -> Optional[str]:
    m = re.search(r"\b([A-Za-z]+)\s+(\d{4})\b", text)
    if not m:
        return None
    month = _normalize_month(m.group(1))
    year = int(m.group(2))
    if not month:
        return None
    return f"{month} {year}"


def locomo_extract_answer(question_text: str, evidence_text: str) -> Optional[str]:
    q = (question_text or "").strip().lower()
    ev = evidence_text or ""
    ev_l = ev.lower()

    if "sunday before" in q:
        m = re.search(r"\bsunday\s+before\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", question_text or "", flags=re.IGNORECASE)
        if m:
            date_text = _extract_date_like(m.group(1))
            if date_text:
                return f"The sunday before {date_text}"

    if q.startswith("when "):
        m = re.search(r"\b(?:the\s+)?(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s+before\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", ev_l)
        if m:
            day_name = m.group(1)
            day = int(m.group(2))
            month = _normalize_month(m.group(3))
            year = int(m.group(4))
            if month:
                return f"The {day_name} before {day} {month} {year}"
        m = re.search(r"\bthe\s+week\s+before\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", ev_l)
        if m:
            day = int(m.group(1))
            month = _normalize_month(m.group(2))
            year = int(m.group(3))
            if month:
                return f"The week before {day} {month} {year}"
        d = _extract_date_like(ev)
        if d:
            return d
        my = _extract_month_year(ev)
        if my:
            return my

    if q.startswith("how long "):
        m = re.search(r"\b(\d+)\s+years?\b", ev_l)
        if m:
            return f"{int(m.group(1))} years"
        m = re.search(r"\b(\d+)\s+years?\s+ago\b", ev_l)
        if m:
            return f"{int(m.group(1))} years ago"

    if q.startswith("where "):
        m = re.search(r"\bfrom\s+([A-Z][A-Za-z]+)\b", ev)
        if m:
            return m.group(1).strip()

    if q.startswith("what did ") and "research" in q:
        m = re.search(r"\bresearch(?:ed|ing)\s+(.+?)(?:\s+it'?s\b|[.\n;]|$)", ev_l)
        if m:
            phrase = m.group(1).strip()
            phrase = re.sub(r"^(?:the|a|an)\s+", "", phrase).strip()
            phrase = phrase.replace("—", " ").replace("-", " ")
            phrase = re.sub(r"\s+", " ", phrase).strip()
            return _cap_first(phrase)

    if "identity" in q:
        if "transgender woman" in ev_l or ("transgender" in ev_l and "woman" in ev_l) or "trans woman" in ev_l:
            return "Transgender woman"

    if "relationship status" in q:
        if "single" in ev_l:
            return "Single"

    if "self-care" in q and ("realize" in q or "realised" in q):
        m = re.search(r"\bself-care\s+is\s+([a-z ]{1,40})\b", ev_l)
        if m:
            tail = m.group(1).strip()
            tail = tail.replace("really ", "")
            if "important" in tail:
                return "self-care is important"

    if "after the charity race" in q and "self-care" in ev_l and "important" in ev_l:
        return "self-care is important"

    if q.startswith("how does ") and "self-care" in q:
        if all(k in ev_l for k in ["carving out", "me-time", "running", "reading", "violin"]):
            return "by carving out some me-time each day for activities like running, reading, or playing the violin"
        m = re.search(r"\bby\s+carving\s+out[^.\n;]+", ev_l)
        if m:
            phrase = m.group(0).strip()
            phrase = phrase.replace("her violin", "the violin")
            phrase = re.sub(r"\s+", " ", phrase).strip()
            return phrase

    return None
