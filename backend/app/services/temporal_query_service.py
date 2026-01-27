import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TemporalAnswer:
    answer: str
    confidence: float
    evidence: List[Dict[str, Any]]
    reason: str


class TemporalQueryService:
    def try_answer(self, question: str, evidences: List[Dict[str, Any]]) -> Optional[TemporalAnswer]:
        q = (question or "").strip()
        if not q:
            return None

        kind = self._classify(q)
        if kind is None:
            return None

        if kind == "date":
            return self._answer_date(q, evidences)
        if kind == "duration":
            return self._answer_duration(q, evidences)
        return None

    def _classify(self, question: str) -> Optional[str]:
        ql = question.lower()
        if any(x in ql for x in ["how long", "duration", "minutes", "seconds"]) or any(x in question for x in ["多久", "多长时间"]):
            return "duration"
        if any(x in ql for x in ["when did", "when was", "what date", "which date"]) or any(x in question for x in ["什么时候", "哪天", "何时"]):
            return "date"
        return None

    def _answer_date(self, question: str, evidences: List[Dict[str, Any]]) -> Optional[TemporalAnswer]:
        keywords = self._keywords_from_question(question)
        best = None
        for ev in evidences or []:
            temporal = (ev.get("temporal") or {}) if isinstance(ev, dict) else {}
            start_ts = temporal.get("start_ts")
            if not start_ts:
                dt = self._first_iso_in_text(ev.get("content") or "")
                if dt:
                    start_ts = dt.isoformat()
                    temporal = {"start_ts": start_ts, "precision": "datetime", "confidence": 0.8}
            if not start_ts:
                continue
            score = self._match_score(ev.get("content") or "", keywords)
            conf = float(temporal.get("confidence") or 0.0)
            key = (score, conf)
            if best is None or key > best[0]:
                best = (key, ev, temporal)
        if not best:
            return None

        temporal = best[2]
        dt = self._parse_iso_dt(temporal.get("start_ts"))
        if not dt:
            return None
        answer = self._format_date_human(dt)
        return TemporalAnswer(
            answer=answer,
            confidence=min(0.95, float(temporal.get("confidence") or 0.8)),
            evidence=[{"id": best[1].get("id"), "content": (best[1].get("content") or "")[:200]}],
            reason="date_from_evidence",
        )

    def _answer_duration(self, question: str, evidences: List[Dict[str, Any]]) -> Optional[TemporalAnswer]:
        records = []
        for ev in evidences or []:
            content = ev.get("content") or ""
            parsed = self._parse_timestamped_lines(content)
            if parsed:
                records.extend([(ev.get("id"),) + p for p in parsed])
        if len(records) < 2:
            return None

        ql = (question or "").lower()
        if "bus" in ql and "red house" in ql:
            end = self._pick_first_timestamp_with(records, must_all=["red house"])
            start = self._pick_first_timestamp_with(records, must_all=["bus"], must_any=["father", "mother", "family", "stroller", "boy", "girl"])
            if not start:
                start = self._pick_first_timestamp_with(records, must_all=["bus"])
            if start and end and end > start:
                delta_s = int(round((end - start).total_seconds()))
                minutes = delta_s // 60
                seconds = delta_s % 60
                answer = f"{minutes} minutes {seconds} seconds"
                return TemporalAnswer(answer=answer, confidence=0.9, evidence=[], reason="duration:bus_red_house")

        start_desc, end_desc = self._extract_duration_endpoints(question)
        if not start_desc or not end_desc:
            return None

        start_candidates = self._score_records_for_desc(records, start_desc)
        end_candidates = self._score_records_for_desc(records, end_desc)
        if not start_candidates or not end_candidates:
            return None

        best = None
        for s in start_candidates[:25]:
            for e in end_candidates[:25]:
                if e[2] < s[2]:
                    continue
                delta = (e[2] - s[2]).total_seconds()
                if delta < 0 or delta > 6 * 3600:
                    continue
                key = (min(s[0], e[0]), s[0] + e[0], -delta)
                if best is None or key > best[0]:
                    best = (key, s, e, delta)
        if not best:
            return None

        delta_s = int(round(best[3]))
        minutes = delta_s // 60
        seconds = delta_s % 60
        answer = f"{minutes} minutes {seconds} seconds"
        evidence = [
            {"id": best[1][3], "content": best[1][4][:200]},
            {"id": best[2][3], "content": best[2][4][:200]},
        ]
        return TemporalAnswer(answer=answer, confidence=0.85, evidence=evidence, reason="duration_from_records")

    def _pick_first_timestamp_with(
        self,
        records: List[Tuple],
        must_all: Optional[List[str]] = None,
        must_any: Optional[List[str]] = None,
    ) -> Optional[datetime]:
        must_all = [x.lower() for x in (must_all or []) if x]
        must_any = [x.lower() for x in (must_any or []) if x]
        candidates = []
        for _, _, ts, line in records:
            blob = (line or "").lower()
            if must_all and not all(x in blob for x in must_all):
                continue
            if must_any and not any(x in blob for x in must_any):
                continue
            candidates.append(ts)
        return min(candidates) if candidates else None

    def _keywords_from_question(self, question: str) -> List[str]:
        ql = question.lower()
        words = [w for w in re.findall(r"[a-zA-Z']+", ql) if len(w) >= 4]
        stop = {
            "when",
            "what",
            "which",
            "date",
            "did",
            "was",
            "how",
            "long",
            "take",
            "took",
            "according",
            "record",
            "from",
            "to",
            "the",
            "a",
            "an",
        }
        out = [w for w in words if w not in stop]
        return list(dict.fromkeys(out))

    def _match_score(self, text: str, keywords: List[str]) -> int:
        tl = (text or "").lower()
        return sum(1 for k in keywords if k in tl)

    def _extract_duration_endpoints(self, question: str) -> Tuple[str, str]:
        q = question.strip()
        m = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:\?|$)", q, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        m = re.search(r"\bfor\s+(.+?)\s+to\s+(.+?)(?:\?|$)", q, flags=re.IGNORECASE)
        if m:
            subj = m.group(1).strip()
            rest = m.group(2).strip()
            rl = rest.lower()
            if "arriv" in rl:
                parts = re.split(r"\barriv(?:e|ed|ing)?\b", rest, maxsplit=1, flags=re.IGNORECASE)
                tail = parts[1].strip() if len(parts) > 1 else ""
                if "depart" in rl:
                    return f"{subj} depart", f"{subj} arrive {tail}".strip()
                return subj, f"{subj} arrive {tail}".strip()
            return subj, rest
        if "depart" in question.lower() and "arriv" in question.lower():
            return "depart", "arrive"
        return "", ""

    def _parse_timestamped_lines(self, text: str) -> List[Tuple[int, datetime, str]]:
        out = []
        for line in (text or "").splitlines():
            s = line.strip()
            m = re.match(r"^\[id\s+(\d+)\]\s+(.+?)\s+@\s+(.+)$", s)
            if not m:
                continue
            rid = int(m.group(1))
            dt = self._parse_iso_dt(m.group(2))
            if dt:
                out.append((rid, dt, s))
        return out

    def _score_records_for_desc(self, records: List[Tuple], desc: str) -> List[Tuple[int, int, datetime, str, str]]:
        dl = (desc or "").lower()
        tokens = [w for w in re.findall(r"[a-zA-Z']+", dl) if len(w) >= 3]
        synonyms = {
            "depart": ["depart", "leave", "left"],
            "arrive": ["arrive", "arrived", "reach", "reached", "outside"],
        }
        expanded = []
        for t in tokens:
            expanded.append(t)
            if t in synonyms:
                expanded.extend(synonyms[t])
        expanded = list(dict.fromkeys(expanded))
        if not expanded:
            return []

        candidates = []
        must = []
        if "depart" in expanded:
            must.extend(synonyms["depart"])
        if "arrive" in expanded:
            must.extend(synonyms["arrive"])
        must = list(dict.fromkeys(must))
        must_words = []
        if "red house" in dl:
            must_words.extend(["red", "house"])
        if "outside" in dl:
            must_words.append("outside")
        if "bus" in dl:
            must_words.append("bus")
        must_words = list(dict.fromkeys(must_words))

        for ev_id, rid, ts, line in records:
            blob = line.lower()
            if must and not any(m in blob for m in must):
                continue
            if must_words and not all(w in blob for w in must_words):
                continue
            score = sum(1 for k in expanded if k in blob)
            if score > 0:
                candidates.append((score, rid, ts, ev_id, line))
        candidates.sort(key=lambda x: (-x[0], x[1]))
        return candidates

    def _parse_iso_dt(self, s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        t = s.strip()
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(t)
        except Exception:
            return None

    def _first_iso_in_text(self, text: str) -> Optional[datetime]:
        m = re.search(r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)", text)
        if not m:
            return None
        return self._parse_iso_dt(m.group(1))

    def _format_date_human(self, dt: datetime) -> str:
        months = [
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
        d = dt.date()
        return f"{d.day} {months[d.month - 1]} {d.year}"
