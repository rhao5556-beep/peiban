import re
from typing import Any, Dict, List, Optional, Tuple


_INTENT_DURATION = {"duration"}
_INTENT_COST = {"cost"}
_INTENT_WHEN = {"when"}
_INTENT_YEAR = {"year"}
_INTENT_MONTH = {"month"}
_INTENT_IDENTITY = {"identity"}
_INTENT_RESEARCH = {"research"}
_INTENT_LIKES = {"likes"}
_INTENT_COMMON = {"common"}

_RE_EXCERPT_HEADER = re.compile(r"(?i)^\s*below is the record excerpt\.", re.MULTILINE)
_RE_TIME_HMS = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d):([0-5]\d)\b")
_RE_TIME_HM = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def compute_answer_from_facts(message: str, facts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    intents = detect_intents(message)
    if not intents or not facts:
        return None

    if "duration" in intents:
        seconds = _pick_duration_seconds(facts)
        if seconds is not None:
            return {
                "kind": "duration",
                "answer": format_duration(seconds),
                "seconds": seconds,
                "evidence": _filter_evidence(facts, {"LASTED"}),
            }

    if "cost" in intents:
        cost = _pick_cost(facts)
        if cost is not None:
            value, unit = cost
            return {
                "kind": "cost",
                "answer": f"{value:g} {unit}",
                "value": value,
                "unit": unit,
                "evidence": _filter_evidence(facts, {"COST"}),
            }

    if "when" in intents:
        d = _pick_date(facts)
        if d is None:
            r = _pick_timerange(facts)
            if r is not None:
                start, end = r
                return {
                    "kind": "when_range",
                    "answer": f"{start} to {end}",
                    "start": start,
                    "end": end,
                    "evidence": _filter_evidence(facts, {"HAPPENED_BETWEEN"}),
                }
        else:
            if "year" in intents:
                y = d.split("-")[0]
                return {
                    "kind": "year",
                    "answer": y,
                    "year": y,
                    "evidence": _filter_evidence(facts, {"HAPPENED_AT"}),
                }
            if "month" in intents:
                y, m, _ = d.split("-")
                mon = _month_name(int(m))
                return {
                    "kind": "month",
                    "answer": f"{mon}, {y}",
                    "month": f"{y}-{m}",
                    "evidence": _filter_evidence(facts, {"HAPPENED_AT"}),
                }
            return {
                "kind": "when",
                "answer": d,
                "date": d,
                "evidence": _filter_evidence(facts, {"HAPPENED_AT"}),
            }

    if "research" in intents:
        t = _pick_single_target(facts, {"RESEARCHED"})
        if t is not None:
            return {
                "kind": "research",
                "answer": t,
                "evidence": _filter_evidence(facts, {"RESEARCHED"}),
            }

    if "likes" in intents:
        t = _pick_single_target(facts, {"LIKES"})
        if t is not None:
            return {
                "kind": "likes",
                "answer": t,
                "evidence": _filter_evidence(facts, {"LIKES"}),
            }

    if "identity" in intents:
        t = _pick_single_target(facts, {"IS"})
        if t is not None:
            return {
                "kind": "identity",
                "answer": t,
                "evidence": _filter_evidence(facts, {"IS"}),
            }

    if "common" in intents:
        t = _pick_single_target(facts, {"SHARES"})
        if t is not None:
            return {
                "kind": "common",
                "answer": t,
                "evidence": _filter_evidence(facts, {"SHARES"}),
            }

    return None


def compute_answer_from_record_excerpt(message: str) -> Optional[Dict[str, Any]]:
    if not message or not _RE_EXCERPT_HEADER.search(message):
        return None
    intents = detect_intents(message)
    if not intents:
        return None

    if "duration" in intents:
        seconds = _compute_duration_seconds_from_excerpt(message)
        if seconds is None:
            return None
        evidence = _pick_excerpt_evidence_lines(message, max_lines=5)
        return {
            "kind": "duration",
            "answer": format_duration(seconds),
            "seconds": seconds,
            "evidence": [{"relation": "LASTED", "target": str(seconds), "excerpt": evidence}],
        }

    return None


def detect_intents(message: str) -> set[str]:
    m = (message or "").lower()
    intents: set[str] = set()

    if any(k in m for k in ["多久", "多长", "持续", "how long", "duration", "take for", "took"]):
        intents |= _INTENT_DURATION

    if any(k in m for k in ["多少钱", "花了", "费用", "cost", "how much", "price", "spent"]):
        intents |= _INTENT_COST

    if any(k in m for k in ["什么时候", "哪天", "几号", "when", "date", "what day"]):
        intents |= _INTENT_WHEN

    if any(k in m for k in ["哪年", "几年", "what year", "year"]):
        intents |= _INTENT_WHEN
        intents |= _INTENT_YEAR

    if any(k in m for k in ["几月", "哪个月", "what month", "month"]):
        intents |= _INTENT_WHEN
        intents |= _INTENT_MONTH

    if any(k in m for k in ["谁是", "是什么人", "who is", "what is"]):
        intents |= _INTENT_IDENTITY

    if any(k in m for k in ["研究", "research", "look up", "researched"]):
        intents |= _INTENT_RESEARCH

    if any(k in m for k in ["喜欢", "like", "likes", "love", "enjoy"]):
        intents |= _INTENT_LIKES

    if any(k in m for k in ["共同", "有什么共同", "common", "in common", "both"]):
        intents |= _INTENT_COMMON

    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", m):
        intents |= _INTENT_WHEN

    return intents


def _month_name(m: int) -> str:
    names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    if 1 <= int(m) <= 12:
        return names[int(m) - 1]
    return "Unknown"


def format_duration(seconds: int) -> str:
    if seconds < 0:
        seconds = -seconds

    mins, sec = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)

    parts = []
    if days:
        parts.append(f"{days} days")
    if hrs:
        parts.append(f"{hrs} hours")
    if mins:
        parts.append(f"{mins} minutes")
    if sec or not parts:
        parts.append(f"{sec} seconds")

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} {parts[1]}"
    return " ".join(parts[:3])


def _pick_duration_seconds(facts: List[Dict[str, Any]]) -> Optional[int]:
    candidates = []
    for f in facts:
        if str(f.get("relation", "")).upper() != "LASTED":
            continue
        t = str(f.get("target", "")).strip()
        if not t:
            continue
        try:
            candidates.append(int(float(t)))
        except Exception:
            continue

    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return candidates[0]
    return None


def _pick_cost(facts: List[Dict[str, Any]]) -> Optional[Tuple[float, str]]:
    candidates = []
    for f in facts:
        if str(f.get("relation", "")).upper() != "COST":
            continue
        t = str(f.get("target", "")).strip()
        if not t:
            continue
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z%]+)\s*$", t)
        if not m:
            continue
        candidates.append((float(m.group(1)), m.group(2)))

    uniq = list(dict.fromkeys(candidates))
    if len(uniq) == 1:
        return uniq[0]
    return None


def _pick_date(facts: List[Dict[str, Any]]) -> Optional[str]:
    candidates = []
    for f in facts:
        if str(f.get("relation", "")).upper() != "HAPPENED_AT":
            continue
        t = str(f.get("target", "")).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
            candidates.append(t)

    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return candidates[0]
    return None


def _pick_timerange(facts: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    for f in facts:
        if str(f.get("relation", "")).upper() != "HAPPENED_BETWEEN":
            continue
        t = str(f.get("target", "")).strip()
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$", t)
        if not m:
            continue
        candidates.append((m.group(1), m.group(2)))
    uniq = list(dict.fromkeys(candidates))
    if len(uniq) == 1:
        return uniq[0]
    return None


def _compute_duration_seconds_from_excerpt(message: str) -> Optional[int]:
    times: List[int] = []
    for hh, mm, ss in _RE_TIME_HMS.findall(message):
        times.append(int(hh) * 3600 + int(mm) * 60 + int(ss))
    if not times:
        for hh, mm in _RE_TIME_HM.findall(message):
            times.append(int(hh) * 3600 + int(mm) * 60)
    if len(times) < 2:
        return None
    lo = min(times)
    hi = max(times)
    if hi < lo:
        return None
    return int(hi - lo)


def _pick_excerpt_evidence_lines(message: str, max_lines: int) -> List[str]:
    lines = []
    for ln in (message or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.lower().startswith("question:"):
            break
        raw = s.lstrip(">").strip()
        if "[id " in raw:
            lines.append(raw)
    return lines[:max_lines]


def _filter_evidence(facts: List[Dict[str, Any]], relation_types: set[str]) -> List[Dict[str, Any]]:
    out = []
    rels = {r.upper() for r in relation_types}
    for f in facts:
        if str(f.get("relation", "")).upper() in rels:
            out.append(f)
    return out[:5]


def _pick_single_target(facts: List[Dict[str, Any]], relation_types: set[str]) -> Optional[str]:
    rels = {r.upper() for r in relation_types}
    candidates = []
    for f in facts:
        if str(f.get("relation", "")).upper() not in rels:
            continue
        t = str(f.get("target", "")).strip()
        if not t:
            continue
        candidates.append(t)
    uniq = list(dict.fromkeys(candidates))
    if len(uniq) == 1:
        return uniq[0]
    return None
