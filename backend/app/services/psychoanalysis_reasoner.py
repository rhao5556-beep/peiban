import re
from typing import Any, Dict, List, Optional


_RE_EXCERPT_HEADER = re.compile(r"(?i)^\s*below is the record excerpt\.", re.MULTILINE)


def compute_psychoanalysis_from_record_excerpt(message: str) -> Optional[Dict[str, Any]]:
    if not message or not _RE_EXCERPT_HEADER.search(message):
        return None

    q = _extract_question(message)
    excerpt = _extract_excerpt_text(message)
    if not q or not excerpt:
        return None

    signals = extract_psycho_signals(excerpt)
    return generate_psycho_hypothesis(q, signals)


def extract_psycho_signals(excerpt: str) -> Dict[str, Any]:
    low = (excerpt or "").lower()
    signals: Dict[str, Any] = {
        "risk_penalty": any(k in low for k in ["penalty", "penalties", "risk", "fine", "punish", "punishment"]),
        "authority_father": any(k in low for k in ["father", "authority"]),
        "public_challenge": any(k in low for k in ["public", "publicly", "challenge", "question"]),
        "evidence_lines": _pick_excerpt_lines(excerpt, max_lines=5),
    }
    return signals


def generate_psycho_hypothesis(question: str, signals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    q = (question or "").strip().lower()
    if not q:
        return None

    evidence = signals.get("evidence_lines") or []
    if not evidence:
        return None

    if any(k in q for k in ["prioritize", "most important", "priority"]) and signals.get("risk_penalty"):
        return {
            "kind": "psychoanalysis",
            "answer": "Avoiding potential risks and penalties.",
            "evidence": evidence,
            "signals": {"risk_penalty": True},
        }

    if any(k in q for k in ["bottom line", "bottom lines", "threshold", "losses"]) and signals.get("authority_father") and signals.get("public_challenge"):
        return {
            "kind": "psychoanalysis",
            "answer": "Publicly challenging or questioning the father's authority.",
            "evidence": evidence,
            "signals": {"authority_father": True, "public_challenge": True},
        }

    return None


def _extract_question(message: str) -> str:
    for ln in (message or "").splitlines():
        s = ln.strip()
        if s.lower().startswith("question:"):
            return s.split(":", 1)[1].strip()
    return ""


def _extract_excerpt_text(message: str) -> str:
    lines: List[str] = []
    in_excerpt = False
    for ln in (message or "").splitlines():
        s = ln.rstrip("\n")
        if not in_excerpt:
            if _RE_EXCERPT_HEADER.match(s.strip()):
                in_excerpt = True
            continue
        if s.strip().lower().startswith("question:"):
            break
        raw = s.strip()
        raw = raw.lstrip(">").strip()
        if "[id " in raw:
            lines.append(raw)
    return "\n".join(lines).strip()


def _pick_excerpt_lines(excerpt: str, max_lines: int) -> List[str]:
    out: List[str] = []
    for ln in (excerpt or "").splitlines():
        s = ln.strip()
        if s:
            out.append(s)
        if len(out) >= max_lines:
            break
    return out
