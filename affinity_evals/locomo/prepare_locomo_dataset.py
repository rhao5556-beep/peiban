import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


_DIA_ID_RE = re.compile(r"^D(\d+):(\d+)$", flags=re.IGNORECASE)
_SESSION_DT_RE = re.compile(
    r"\bon\s+(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})\b",
    flags=re.IGNORECASE,
)


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class ParsedDiaId:
    session_idx: int
    turn_idx: int


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_dia_id(dia_id: str) -> Optional[ParsedDiaId]:
    m = _DIA_ID_RE.match((dia_id or "").strip())
    if not m:
        return None
    return ParsedDiaId(session_idx=int(m.group(1)), turn_idx=int(m.group(2)))


def iter_sessions(conversation: Dict[str, Any]) -> Iterable[Tuple[int, str, List[Dict[str, Any]]]]:
    for k, v in conversation.items():
        m = re.match(r"^session_(\d+)$", k)
        if not m:
            continue
        idx = int(m.group(1))
        if not isinstance(v, list):
            continue
        dt = conversation.get(f"session_{idx}_date_time", "")
        dt_str = str(dt) if dt is not None else ""
        yield idx, dt_str, v


def _parse_session_base_date(session_date_time: str) -> Optional[date]:
    m = _SESSION_DT_RE.search((session_date_time or "").strip())
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).strip().lower()
    year = int(m.group(3))
    month = MONTHS.get(month_name)
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _append_relative_hints(text: str, base: Optional[date]) -> str:
    if not base:
        return text
    t = text
    low = text.lower()
    if "yesterday" in low:
        t = f"{t} | yesterday={base - timedelta(days=1):%Y-%m-%d}"
    if "today" in low:
        t = f"{t} | today={base:%Y-%m-%d}"
    if "tomorrow" in low:
        t = f"{t} | tomorrow={base + timedelta(days=1):%Y-%m-%d}"
    return t


def normalize_turn_text(turn: Dict[str, Any], base_date: Optional[date]) -> str:
    speaker = str(turn.get("speaker") or "").strip()
    text = str(turn.get("text") or "").strip()
    dia_id = str(turn.get("dia_id") or "").strip()

    extras: List[str] = []
    blip = turn.get("blip_caption")
    if isinstance(blip, str) and blip.strip():
        extras.append(f"blip_caption={blip.strip()}")
    query = turn.get("query")
    if isinstance(query, str) and query.strip():
        extras.append(f"query={query.strip()}")
    img_url = turn.get("img_url")
    if isinstance(img_url, list) and img_url:
        extras.append(f"img_url_count={len(img_url)}")

    extra_part = f" | {'; '.join(extras)}" if extras else ""
    prefix = f"{dia_id} " if dia_id else ""
    who = f"{speaker}: " if speaker else ""
    content = f"{prefix}{who}{text}{extra_part}".strip()
    return _append_relative_hints(content, base_date).strip()


def build_transcript(conversation: Dict[str, Any]) -> List[str]:
    sessions = sorted(iter_sessions(conversation), key=lambda x: x[0])
    lines: List[str] = []
    for idx, dt, turns in sessions:
        base_date = _parse_session_base_date(dt)
        base_iso = f"{base_date:%Y-%m-%d}" if base_date else ""
        if dt:
            if base_iso:
                lines.append(f"SESSION_{idx} @ {dt} | base_date={base_iso}".strip())
            else:
                lines.append(f"SESSION_{idx} @ {dt}".strip())
        else:
            lines.append(f"SESSION_{idx}".strip())
        for t in turns:
            if not isinstance(t, dict):
                continue
            s = normalize_turn_text(t, base_date=base_date)
            if s:
                lines.append(s)
    return lines


def build_flat_qa(locomo: List[Dict[str, Any]], include_transcript: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    running_id = 100000
    for i, sample in enumerate(locomo):
        if not isinstance(sample, dict):
            continue
        sample_id = str(sample.get("sample_id") or f"sample_{i}")
        conv = sample.get("conversation") or {}
        transcript = build_transcript(conv) if include_transcript and isinstance(conv, dict) else None
        qa_list = sample.get("qa") or []
        if not isinstance(qa_list, list):
            continue
        for qa in qa_list:
            if not isinstance(qa, dict):
                continue
            running_id += 1
            ev = qa.get("evidence") or []
            evidence = [str(x) for x in ev] if isinstance(ev, list) else []
            out.append(
                {
                    "id": running_id,
                    "sample_id": sample_id,
                    "category": qa.get("category"),
                    "question": qa.get("question"),
                    "answer": qa.get("answer"),
                    "evidence": evidence,
                    "transcript": transcript,
                }
            )
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in_path", default=str(Path("data/locomo/locomo10.json").resolve()))
    p.add_argument("--out_path", default=str(Path("outputs/locomo_prepared/locomo10.prepared.json").resolve()))
    p.add_argument("--include_transcript", action="store_true", default=False)
    args = p.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    locomo = _load_json(in_path)
    if not isinstance(locomo, list):
        raise RuntimeError("locomo10.json must be a list")

    prepared = build_flat_qa(locomo, include_transcript=bool(args.include_transcript))
    out_path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
