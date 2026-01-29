import re
from typing import Dict, List

from app.services.number_normalizer import parse_number_token


_NUM = r"(\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万萬亿点]+|[a-zA-Z][a-zA-Z\\s-]{0,30})"

_CNY_RE = re.compile(_NUM + r"\s*(元|块|RMB|rmb|¥)")
_KM_RE = re.compile(_NUM + r"\s*(km|KM|公里)")
_M_RE = re.compile(_NUM + r"\s*(m|M|米)\b")
_CELSIUS_RE = re.compile(_NUM + r"\s*(℃|°C|C)")
_PCT_RE = re.compile(_NUM + r"\s*%")


def extract_quantities(text: str) -> List[Dict]:
    out: List[Dict] = []
    if not text:
        return out

    for v, _ in _CNY_RE.findall(text):
        n = parse_number_token(v)
        if n is not None:
            out.append({"value": float(n), "unit": "CNY", "raw": f"{v}元"})

    for v, _ in _KM_RE.findall(text):
        n = parse_number_token(v)
        if n is not None:
            out.append({"value": float(n), "unit": "km", "raw": f"{v}km"})

    for v, _ in _M_RE.findall(text):
        n = parse_number_token(v)
        if n is not None:
            out.append({"value": float(n), "unit": "m", "raw": f"{v}m"})

    for v, _ in _CELSIUS_RE.findall(text):
        n = parse_number_token(v)
        if n is not None:
            out.append({"value": float(n), "unit": "C", "raw": f"{v}C"})

    for v in _PCT_RE.findall(text):
        n = parse_number_token(v)
        if n is not None:
            out.append({"value": float(n), "unit": "%", "raw": f"{v}%"})

    dedup = []
    seen = set()
    for q in out:
        key = (q["unit"], q["value"])
        if key not in seen:
            dedup.append(q)
            seen.add(key)
    return dedup
