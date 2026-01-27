import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple


class TemporalExtractor:
    def extract(self, text: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        raw = text or ""
        ref = reference_time or datetime.utcnow().replace(tzinfo=timezone.utc)
        ref = self._ensure_tz(ref)

        tagged_ts = self._extract_tagged_ts(raw)
        if tagged_ts:
            ref = tagged_ts

        rel = self._extract_relative_date(raw, ref)
        if rel:
            start, precision, source = rel
            return {
                "start_ts": start.isoformat(),
                "end_ts": None,
                "precision": precision,
                "confidence": 0.9,
                "source": source,
                "reference_ts": ref.isoformat(),
            }

        dt = self._extract_iso_datetime(raw)
        if dt:
            return {
                "start_ts": dt.isoformat(),
                "end_ts": None,
                "precision": "datetime",
                "confidence": 1.0,
                "source": "iso_datetime",
                "reference_ts": ref.isoformat(),
            }

        d = self._extract_date_literal(raw)
        if d:
            return {
                "start_ts": d.isoformat(),
                "end_ts": None,
                "precision": "date",
                "confidence": 0.95,
                "source": "date_literal",
                "reference_ts": ref.isoformat(),
            }

        fuzzy = self._extract_fuzzy_time(raw)
        if fuzzy:
            return {
                "start_ts": None,
                "end_ts": None,
                "precision": "fuzzy",
                "confidence": 0.3,
                "source": "fuzzy",
                "reference_ts": ref.isoformat(),
            }

        return {
            "start_ts": None,
            "end_ts": None,
            "precision": "none",
            "confidence": 0.0,
            "source": "none",
            "reference_ts": ref.isoformat(),
        }

    def _ensure_tz(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _extract_tagged_ts(self, text: str) -> Optional[datetime]:
        m = re.search(r"\bts=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)", text)
        if m:
            dt = self._parse_iso_dt(m.group(1))
            if dt:
                return dt
        m = re.search(r"^\[id\s+\d+\]\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+@", text.strip())
        if m:
            dt = self._parse_iso_dt(m.group(1))
            if dt:
                return dt
        return None

    def _extract_relative_date(self, text: str, ref: datetime) -> Optional[Tuple[datetime, str, str]]:
        lower = (text or "").lower()
        if "yesterday" in lower or "昨天" in text:
            return ref - timedelta(days=1), "date", "relative:yesterday"
        if "today" in lower or "今天" in text:
            return ref, "date", "relative:today"
        if "tomorrow" in lower or "明天" in text:
            return ref + timedelta(days=1), "date", "relative:tomorrow"
        if "last week" in lower or "上周" in text:
            return ref - timedelta(days=7), "date", "relative:last_week"
        if "last month" in lower or "上个月" in text:
            return ref - timedelta(days=30), "date", "relative:last_month"
        if "last year" in lower or "去年" in text:
            return ref - timedelta(days=365), "date", "relative:last_year"
        return None

    def _extract_iso_datetime(self, text: str) -> Optional[datetime]:
        m = re.search(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)",
            text,
        )
        if not m:
            return None
        return self._parse_iso_dt(m.group(1))

    def _parse_iso_dt(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        t = s.strip()
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(t)
        except Exception:
            return None

    def _extract_date_literal(self, text: str) -> Optional[datetime]:
        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            except Exception:
                return None

        month_map = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
        if m:
            day = int(m.group(1))
            mon = month_map.get(m.group(2).lower())
            year = int(m.group(3))
            if mon:
                try:
                    return datetime(year, mon, day, tzinfo=timezone.utc)
                except Exception:
                    return None
        return None

    def _extract_fuzzy_time(self, text: str) -> bool:
        if any(x in text for x in ["傍晚", "晚上", "早上", "中午", "那天", "一会儿"]):
            return True
        lower = (text or "").lower()
        return any(x in lower for x in ["sometime", "later", "that day", "evening", "morning"])

