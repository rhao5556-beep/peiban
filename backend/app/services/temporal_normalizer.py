import re
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from zoneinfo import ZoneInfo

from app.services.number_normalizer import parse_number_token


_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_EN_DATE_MDY_RE = re.compile(
    r"(?i)\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s+(\d{1,2})(?:,)?\s+(\d{4})\b"
)
_EN_DATE_DMY_RE = re.compile(
    r"(?i)\b(\d{1,2})\s+("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")(?:,)?\s+(\d{4})\b"
)

_EN_MONTH = {
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

_EN_DURATION_RE = re.compile(
    r"(?P<n>\d+|[a-zA-Z][a-zA-Z\s-]{0,30})\s*(?P<u>hours?|hrs?|minutes?|mins?|seconds?|secs?)\b",
    re.IGNORECASE,
)
_CN_DURATION_RE = re.compile(r"(?P<n>\d+|[零〇一二两三四五六七八九十百千万萬亿点]+)\s*(?P<u>天|小时|分钟|分|秒)")

_CN_REL_DAY = {
    "今天": 0,
    "今日": 0,
    "昨天": -1,
    "昨日": -1,
    "前天": -2,
    "明天": 1,
    "明日": 1,
    "后天": 2,
}

_CN_WEEKDAY = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

_EN_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_CN_REL_WEEKDAY_RE = re.compile(r"(上周|下周|本周|这周|本星期|这个星期|上星期|下星期)\s*(?:星期|周)?([一二三四五六日天])")
_CN_REL_N_DAYS_RE = re.compile(r"([零〇一二两三四五六七八九十百千万萬亿\d]+)\s*天(后|前)")
_CN_REL_MONTH_RE = re.compile(r"(下个月|上个月|这个月|本月)")
_EN_REL_WEEKDAY_RE = re.compile(r"(?i)\b(last|next|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b")
_EN_REL_IN_DAYS_RE = re.compile(r"(?i)\b(in)\s+([a-zA-Z][a-zA-Z\s-]{0,30}|\d+)\s+days?\b")
_EN_REL_DAYS_LATER_RE = re.compile(r"(?i)\b([a-zA-Z][a-zA-Z\s-]{0,30}|\d+)\s+days?\s+(later|after)\b")
_EN_REL_DAYS_AGO_RE = re.compile(r"(?i)\b([a-zA-Z][a-zA-Z\s-]{0,30}|\d+)\s+days?\s+ago\b")
_EN_REL_MONTH_RE = re.compile(r"(?i)\b(last|next|this)\s+month\b")
_EN_REL_YEAR_RE = re.compile(r"(?i)\b(last|next|this)\s+year\b")
_EN_REL_TODAY = re.compile(r"(?i)\b(today|tomorrow|yesterday)\b")


def extract_dates(text: str) -> List[str]:
    out: List[str] = []
    if not text:
        return out

    for y, m, d in _ISO_DATE_RE.findall(text):
        out.append(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")

    for y, m, d in _CN_DATE_RE.findall(text):
        out.append(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")

    for mon, d, y in _EN_DATE_MDY_RE.findall(text):
        mm = _EN_MONTH.get(mon.lower()[:3] if len(mon) > 3 else mon.lower(), _EN_MONTH.get(mon.lower(), 0))
        if mm:
            out.append(f"{int(y):04d}-{int(mm):02d}-{int(d):02d}")

    for d, mon, y in _EN_DATE_DMY_RE.findall(text):
        mm = _EN_MONTH.get(mon.lower()[:3] if len(mon) > 3 else mon.lower(), _EN_MONTH.get(mon.lower(), 0))
        if mm:
            out.append(f"{int(y):04d}-{int(mm):02d}-{int(d):02d}")

    return list(dict.fromkeys(out))


def extract_temporal_constraints(
    text: str,
    anchor_dt: Optional[datetime] = None,
    timezone: str = "UTC",
) -> List[Dict[str, Any]]:
    tz = _safe_zoneinfo(timezone)
    anchor = (anchor_dt or datetime.now(tz)).astimezone(tz)

    out: List[Dict[str, Any]] = []

    lower = (text or "").lower()
    dates = extract_dates(text)
    if dates:
        if "week before" in lower:
            y, m, d = (int(x) for x in dates[0].split("-"))
            anchor_day = date(y, m, d)
            start = (anchor_day - timedelta(days=7)).isoformat()
            end = (anchor_day - timedelta(days=1)).isoformat()
            out.append(
                {
                    "kind": "range",
                    "start": start,
                    "end": end,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.9,
                }
            )
            return out
        if "sunday before" in lower:
            y, m, d = (int(x) for x in dates[0].split("-"))
            anchor_day = date(y, m, d)
            back = (anchor_day.weekday() + 1) % 7
            if back == 0:
                back = 7
            target = (anchor_day - timedelta(days=back)).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": target,
                    "end": target,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.9,
                }
            )
            return out

    for iso in extract_dates(text):
        out.append(
            {
                "kind": "point",
                "start": iso,
                "end": iso,
                "precision": "day",
                "timezone": timezone,
                "anchor_used": anchor.isoformat(),
                "confidence": 1.0,
            }
        )

    rel = _extract_relative_constraints(text, anchor, timezone)
    out.extend(rel)

    return out


def _extract_relative_constraints(text: str, anchor: datetime, timezone: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not text:
        return out

    for k, delta in _CN_REL_DAY.items():
        if k in text:
            d = (anchor.date() + timedelta(days=delta)).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": d,
                    "end": d,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.9,
                }
            )
            break

    m = _CN_REL_N_DAYS_RE.search(text)
    if m:
        n = parse_number_token(m.group(1))
        if n is not None:
            days = int(n)
            sign = 1 if m.group(2) == "后" else -1
            d = (anchor.date() + timedelta(days=sign * days)).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": d,
                    "end": d,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.85,
                }
            )

    m = _CN_REL_WEEKDAY_RE.search(text)
    if m:
        prefix = m.group(1)
        wd = _CN_WEEKDAY.get(m.group(2))
        if wd is not None:
            base = anchor.date()
            start_of_week = base - timedelta(days=base.weekday())
            if prefix in ("上周", "上星期"):
                start_of_week -= timedelta(days=7)
            elif prefix in ("下周", "下星期"):
                start_of_week += timedelta(days=7)
            target = (start_of_week + timedelta(days=wd)).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": target,
                    "end": target,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.85,
                }
            )

    m = _CN_REL_MONTH_RE.search(text)
    if m:
        which = m.group(1)
        y = anchor.year
        mo = anchor.month
        if which == "上个月":
            mo -= 1
            if mo == 0:
                mo = 12
                y -= 1
        elif which == "下个月":
            mo += 1
            if mo == 13:
                mo = 1
                y += 1
        start, end = _month_range(y, mo)
        out.append(
            {
                "kind": "range",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "precision": "day",
                "timezone": timezone,
                "anchor_used": anchor.isoformat(),
                "confidence": 0.8,
            }
        )

    m = _EN_REL_TODAY.search(text)
    if m:
        w = m.group(1).lower()
        delta = 0
        if w == "tomorrow":
            delta = 1
        elif w == "yesterday":
            delta = -1
        d = (anchor.date() + timedelta(days=delta)).isoformat()
        out.append(
            {
                "kind": "point",
                "start": d,
                "end": d,
                "precision": "day",
                "timezone": timezone,
                "anchor_used": anchor.isoformat(),
                "confidence": 0.9,
            }
        )

    m = _EN_REL_IN_DAYS_RE.search(text)
    if m:
        n = parse_number_token(m.group(2))
        if n is not None:
            d = (anchor.date() + timedelta(days=int(n))).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": d,
                    "end": d,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.85,
                }
            )

    m = _EN_REL_DAYS_LATER_RE.search(text)
    if m:
        n = parse_number_token(m.group(1))
        if n is not None:
            d = (anchor.date() + timedelta(days=int(n))).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": d,
                    "end": d,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.85,
                }
            )

    m = _EN_REL_DAYS_AGO_RE.search(text)
    if m:
        n = parse_number_token(m.group(1))
        if n is not None:
            d = (anchor.date() - timedelta(days=int(n))).isoformat()
            out.append(
                {
                    "kind": "point",
                    "start": d,
                    "end": d,
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.85,
                }
            )

    m = _EN_REL_WEEKDAY_RE.search(text)
    if m:
        which = m.group(1).lower()
        wd = _EN_WEEKDAY.get(m.group(2).lower())
        if wd is not None:
            base = anchor.date()
            days_ahead = wd - base.weekday()
            if which == "this":
                target = base + timedelta(days=days_ahead)
            elif which == "next":
                if days_ahead <= 0:
                    days_ahead += 7
                target = base + timedelta(days=days_ahead)
            else:
                if days_ahead >= 0:
                    days_ahead -= 7
                target = base + timedelta(days=days_ahead)
            out.append(
                {
                    "kind": "point",
                    "start": target.isoformat(),
                    "end": target.isoformat(),
                    "precision": "day",
                    "timezone": timezone,
                    "anchor_used": anchor.isoformat(),
                    "confidence": 0.8,
                }
            )

    m = _EN_REL_MONTH_RE.search(text)
    if m:
        which = m.group(1).lower()
        y = anchor.year
        mo = anchor.month
        if which == "last":
            mo -= 1
            if mo == 0:
                mo = 12
                y -= 1
        elif which == "next":
            mo += 1
            if mo == 13:
                mo = 1
                y += 1
        start, end = _month_range(y, mo)
        out.append(
            {
                "kind": "range",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "precision": "day",
                "timezone": timezone,
                "anchor_used": anchor.isoformat(),
                "confidence": 0.8,
            }
        )

    m = _EN_REL_YEAR_RE.search(text)
    if m:
        which = m.group(1).lower()
        y = anchor.year + (1 if which == "next" else -1 if which == "last" else 0)
        out.append(
            {
                "kind": "range",
                "start": date(y, 1, 1).isoformat(),
                "end": date(y, 12, 31).isoformat(),
                "precision": "day",
                "timezone": timezone,
                "anchor_used": anchor.isoformat(),
                "confidence": 0.75,
            }
        )

    return out


def _month_range(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    if m == 12:
        end = date(y, 12, 31)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return start, end


def _safe_zoneinfo(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except Exception:
        return ZoneInfo("UTC")

def parse_duration_seconds(text: str) -> Optional[int]:
    if not text:
        return None

    total = 0
    found = False

    for m in _EN_DURATION_RE.finditer(text):
        n_val = parse_number_token(m.group("n"))
        if n_val is None:
            continue
        n = int(n_val)
        u = m.group("u").lower()
        found = True
        if u.startswith(("hour", "hr")):
            total += n * 3600
        elif u.startswith(("minute", "min")):
            total += n * 60
        elif u.startswith(("second", "sec")):
            total += n

    for m in _CN_DURATION_RE.finditer(text):
        n_val = parse_number_token(m.group("n"))
        if n_val is None:
            continue
        n = int(n_val)
        u = m.group("u")
        found = True
        if u == "天":
            total += n * 86400
        elif u == "小时":
            total += n * 3600
        elif u in ("分钟", "分"):
            total += n * 60
        elif u == "秒":
            total += n

    return total if found and total > 0 else None
