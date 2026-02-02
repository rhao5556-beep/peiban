import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EvalPayload:
    evidence_text: str
    question_text: str
    session_time: Optional[str]


_SESSION_TIME_RE = re.compile(r"^\s*Session time:\s*(.+)\s*$", flags=re.IGNORECASE | re.MULTILINE)


def extract_eval_payload(message: str) -> EvalPayload:
    s = message or ""
    lower = s.lower()
    q_idx = lower.rfind("question:")
    if q_idx < 0:
        return EvalPayload(evidence_text="", question_text=s.strip(), session_time=None)

    evidence_part = s[:q_idx].strip()
    tail = s[q_idx + len("Question:") :]
    a_m = re.search(r"\n\s*answer\s*:", tail, flags=re.IGNORECASE)
    if a_m:
        question_part = tail[: a_m.start()].strip()
    else:
        question_part = tail.strip()

    ev = evidence_part
    if ev:
        below_idx = evidence_part.lower().find("below is")
        if below_idx >= 0:
            ev = evidence_part[below_idx:].strip()

    st_m = _SESSION_TIME_RE.search(ev)
    session_time = st_m.group(1).strip() if st_m else None

    return EvalPayload(
        evidence_text=ev,
        question_text=question_part if question_part else s.strip(),
        session_time=session_time,
    )

