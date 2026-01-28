from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TemporalParseResult:
    anchor_ts: Optional[datetime]
    speaker: Optional[str]
    day_tag: Optional[str]
    line_no: Optional[int]
    raw_phrases: List[str]
    resolved: Optional[Dict[str, Any]]


class TemporalExtractor:
    def __init__(self):
        self._header_re = re.compile(
            r"^\[(?P<day>D\d+):(?P<line>\d+)\s+ts=(?P<ts>[^\]]+)\]\s+(?P<body>.+)$"
        )

    def extract(self, text: str) -> Dict[str, Any]:
        parsed = self._parse(text)
        meta: Dict[str, Any] = {
            "transcript": {
                "day": parsed.day_tag,
                "line": parsed.line_no,
                "anchor_ts": parsed.anchor_ts.isoformat() if parsed.anchor_ts else None,
            },
            "speaker": parsed.speaker,
        }
        if parsed.raw_phrases or parsed.resolved:
            meta["temporal"] = {
                "raw_phrases": parsed.raw_phrases,
                "anchor_ts": parsed.anchor_ts.isoformat() if parsed.anchor_ts else None,
                "resolved": parsed.resolved,
            }
        return meta

    def _parse(self, text: str) -> TemporalParseResult:
        anchor_ts = None
        speaker = None
        day_tag = None
        line_no = None
        body = text.strip() if text else ""

        m = self._header_re.match(body)
        if m:
            day_tag = m.group("day")
            try:
                line_no = int(m.group("line"))
            except Exception:
                line_no = None
            anchor_ts = self._parse_iso_dt(m.group("ts"))
            body = m.group("body").strip()

        speaker, content = self._split_speaker(body)
        raw_phrases, resolved = self._resolve_relative_time(content, anchor_ts)

        return TemporalParseResult(
            anchor_ts=anchor_ts,
            speaker=speaker,
            day_tag=day_tag,
            line_no=line_no,
            raw_phrases=raw_phrases,
            resolved=resolved,
        )

    def _parse_iso_dt(self, ts: str) -> Optional[datetime]:
        if not ts:
            return None
        ts = ts.strip()
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except Exception:
            return None

    def _split_speaker(self, body: str) -> Tuple[Optional[str], str]:
        if not body:
            return None, ""
        if ":" not in body:
            return None, body.strip()
        left, right = body.split(":", 1)
        speaker = left.strip()
        content = right.strip()
        if not speaker:
            return None, body.strip()
        return speaker, content

    def _resolve_relative_time(self, text: str, anchor: Optional[datetime]) -> Tuple[List[str], Optional[Dict[str, Any]]]:
        if not text:
            return [], None

        lowered = text.lower()
        phrases: List[str] = []

        if "yesterday" in lowered:
            phrases.append("yesterday")
            if anchor:
                day = (anchor - timedelta(days=1)).date()
                return phrases, {
                    "type": "date",
                    "granularity": "day",
                    "value": day.isoformat(),
                }

        if "today" in lowered:
            phrases.append("today")
            if anchor:
                day = anchor.date()
                return phrases, {
                    "type": "date",
                    "granularity": "day",
                    "value": day.isoformat(),
                }

        if "tomorrow" in lowered:
            phrases.append("tomorrow")
            if anchor:
                day = (anchor + timedelta(days=1)).date()
                return phrases, {
                    "type": "date",
                    "granularity": "day",
                    "value": day.isoformat(),
                }

        if "last week" in lowered:
            phrases.append("last week")
            if anchor:
                start = (anchor.date() - timedelta(days=7))
                end = anchor.date()
                return phrases, {
                    "type": "range",
                    "granularity": "week",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }

        if "last month" in lowered:
            phrases.append("last month")
            if anchor:
                y = anchor.year
                m = anchor.month - 1
                if m == 0:
                    y -= 1
                    m = 12
                start = datetime(y, m, 1).date()
                if m == 12:
                    end = datetime(y + 1, 1, 1).date() - timedelta(days=1)
                else:
                    end = datetime(y, m + 1, 1).date() - timedelta(days=1)
                return phrases, {
                    "type": "range",
                    "granularity": "month",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }

        if "last year" in lowered:
            phrases.append("last year")
            if anchor:
                y = anchor.year - 1
                start = datetime(y, 1, 1).date()
                end = datetime(y, 12, 31).date()
                return phrases, {
                    "type": "range",
                    "granularity": "year",
                    "year": y,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }

        return phrases, None

