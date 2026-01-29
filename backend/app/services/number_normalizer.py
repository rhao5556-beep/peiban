import re
from typing import Optional


_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_CN_SMALL_UNITS = {"十": 10, "百": 100, "千": 1000}
_CN_LARGE_UNITS = {"万": 10_000, "萬": 10_000, "亿": 100_000_000}

_EN_SMALL = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

_EN_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def parse_number_token(token: str) -> Optional[float]:
    if not token:
        return None
    token = token.strip()
    if not token:
        return None

    try:
        return float(token)
    except Exception:
        pass

    cn = _parse_chinese_number(token)
    if cn is not None:
        return float(cn)

    en = _parse_english_number(token)
    if en is not None:
        return float(en)

    return None


def _parse_chinese_number(text: str) -> Optional[float]:
    if not text:
        return None

    if any(ch in text for ch in ("点", ".")):
        parts = re.split(r"[点.]", text, maxsplit=1)
        int_part = _parse_chinese_integer(parts[0])
        if int_part is None:
            return None
        frac_part = parts[1] if len(parts) > 1 else ""
        frac_digits = []
        for ch in frac_part:
            if ch in _CN_DIGITS:
                frac_digits.append(str(_CN_DIGITS[ch]))
            elif ch.isdigit():
                frac_digits.append(ch)
            else:
                return None
        frac = float("0." + "".join(frac_digits)) if frac_digits else 0.0
        return float(int_part) + frac

    return _parse_chinese_integer(text)


def _parse_chinese_integer(text: str) -> Optional[int]:
    if not text:
        return None

    if all(ch in _CN_DIGITS for ch in text):
        return int("".join(str(_CN_DIGITS[ch]) for ch in text))

    total = 0
    section = 0
    num = 0
    any_hit = False

    for ch in text:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
            any_hit = True
            continue

        if ch in _CN_SMALL_UNITS:
            unit = _CN_SMALL_UNITS[ch]
            any_hit = True
            if num == 0:
                num = 1
            section += num * unit
            num = 0
            continue

        if ch in _CN_LARGE_UNITS:
            unit = _CN_LARGE_UNITS[ch]
            any_hit = True
            section += num
            num = 0
            total += section * unit
            section = 0
            continue

        return None

    if not any_hit:
        return None

    section += num
    total += section

    if total == 0 and text in ("十",):
        return 10

    return total


def _parse_english_number(text: str) -> Optional[int]:
    if not text:
        return None

    t = text.lower().strip()
    t = re.sub(r"[-_]+", " ", t)
    words = [w for w in re.split(r"\s+", t) if w and w != "and"]
    if not words:
        return None

    total = 0
    current = 0
    any_hit = False

    for w in words:
        if w in _EN_SMALL:
            current += _EN_SMALL[w]
            any_hit = True
            continue
        if w in _EN_TENS:
            current += _EN_TENS[w]
            any_hit = True
            continue
        if w == "hundred":
            if current == 0:
                current = 1
            current *= 100
            any_hit = True
            continue
        if w == "thousand":
            if current == 0:
                current = 1
            total += current * 1000
            current = 0
            any_hit = True
            continue
        return None

    return total + current if any_hit else None

