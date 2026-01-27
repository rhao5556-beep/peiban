import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    if not s:
        return "unknown"
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def _is_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "\n" in t:
        return False
    if "?" in t or "？" in t:
        return t.endswith("?") or t.endswith("？")
    low = t.lower()
    if any(w in low for w in ["who", "what", "when", "where", "why", "how"]):
        return len(t) < 160
    if any(w in t for w in ["吗", "呢", "是否", "是不是", "谁", "什么", "哪里", "怎么", "为什么", "多少"]):
        return len(t) < 160
    return False


def extract_ir_rule(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    if _is_question(text):
        return [], [], 0.0

    t = (text or "").strip()
    if not t:
        return [], [], 0.0

    entities: Dict[str, Dict[str, Any]] = {}
    relations: List[Dict[str, Any]] = []

    def add_entity(name: str, typ: str) -> str:
        eid = _slugify(name)
        if eid not in entities:
            entities[eid] = {"id": eid, "name": name, "type": typ, "confidence": 0.55}
        return eid

    def add_relation(src: str, tgt: str, rel_type: str, desc: str) -> None:
        relations.append(
            {
                "source": src,
                "target": tgt,
                "type": rel_type,
                "desc": desc,
                "weight": 0.55,
                "confidence": 0.55,
            }
        )

    def handle_sentence(sentence: str, speaker: str = "") -> None:
        s = (sentence or "").strip()
        if not s or _is_question(s):
            return
        spk = (speaker or "").strip()

        def resolve_person(name: str) -> str:
            if name.strip().lower() == "i" and spk:
                return spk
            return name

        def clean_event_name(name: str) -> str:
            n = (name or "").strip().strip(" \t\"'“”‘’")
            n = re.sub(r"[。！？!?，,]+$", "", n).strip()
            patterns = [
                r"\s+(?:yesterday|today|tomorrow)\s*$",
                r"\s+last\s+year\s*$",
                r"\s+next\s+year\s*$",
                r"\s+last\s+month\s*$",
                r"\s+next\s+month\s*$",
                r"\s+last\s+week\s*$",
                r"\s+few\s+weeks\s+ago\s*$",
                r"\s+\d+\s+weeks?\s+ago\s*$",
                r"\s+last\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*$",
                r"\s*(?:昨天|今天|明天|去年|明年|上个月|下个月|上上周|上周[一二三四五六日天]?|前几周|几周前)\s*$",
            ]
            for pat in patterns:
                n2 = re.sub(pat, "", n, flags=re.IGNORECASE).strip()
                n = n2
            n = re.sub(r"\s{2,}", " ", n).strip()
            return n or (name or "").strip()

        m = re.search(r"([^\s:：]{1,20})\s*(?:住在|住在了)\s*([^\s，。,.\n]{1,20})", s)
        if m:
            p, loc = resolve_person(m.group(1)), m.group(2)
            p_id = add_entity(p, "Person")
            l_id = add_entity(loc, "Location")
            add_relation(p_id, l_id, "LIVES_IN", f"{p}住在{loc}")

        m = re.search(r"([^\s:：]{1,20})\s*(?:来自|从)\s*([^\s，。,.\n]{1,20})", s)
        if m:
            p, loc = resolve_person(m.group(1)), m.group(2)
            p_id = add_entity(p, "Person")
            l_id = add_entity(loc, "Location")
            add_relation(p_id, l_id, "FROM", f"{p}来自{loc}")

        m = re.search(r"([^\s:：]{1,20})\s*不喜欢\s*([^\s，。,.\n]{1,30})", s)
        if m:
            p, thing = resolve_person(m.group(1)), m.group(2)
            p_id = add_entity(p, "Person")
            th_id = add_entity(thing, "Preference")
            add_relation(p_id, th_id, "DISLIKES", f"{p}不喜欢{thing}")

        m = re.search(r"([^\s:：]{1,20})\s*喜欢\s*([^\s，。,.\n]{1,30})", s)
        if m and "不喜欢" not in s:
            p, thing = resolve_person(m.group(1)), m.group(2)
            p_id = add_entity(p, "Person")
            th_id = add_entity(thing, "Preference")
            add_relation(p_id, th_id, "LIKES", f"{p}喜欢{thing}")

        m = re.search(r"([^\s:：]{1,20})的(妈妈|母亲|爸爸|父亲)\b", s)
        if m:
            child, rel = m.group(1), m.group(2)
            c_id = add_entity(child, "Person")
            parent_name = f"{child}的{rel}"
            p_id = add_entity(parent_name, "Person")
            add_relation(p_id, c_id, "PARENT_OF", parent_name)

        m = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+lives\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
            s,
        )
        if m:
            p, loc = m.group(1), m.group(2)
            p_id = add_entity(p, "Person")
            l_id = add_entity(loc, "Location")
            add_relation(p_id, l_id, "LIVES_IN", f"{p} lives in {loc}")

        m = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+is\s+from\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
            s,
        )
        if m:
            p, loc = m.group(1), m.group(2)
            p_id = add_entity(p, "Person")
            l_id = add_entity(loc, "Location")
            add_relation(p_id, l_id, "FROM", f"{p} is from {loc}")

        m = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+does\s+not\s+like\s+([A-Za-z0-9][^,\.\\n]{1,40})",
            s,
        )
        if m:
            p, thing = m.group(1), m.group(2).strip()
            p_id = add_entity(p, "Person")
            th_id = add_entity(thing, "Preference")
            add_relation(p_id, th_id, "DISLIKES", f"{p} does not like {thing}")

        m = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+likes\s+([A-Za-z0-9][^,\.\\n]{1,40})",
            s,
        )
        if m and "does not like" not in s.lower():
            p, thing = m.group(1), m.group(2).strip()
            p_id = add_entity(p, "Person")
            th_id = add_entity(thing, "Preference")
            add_relation(p_id, th_id, "LIKES", f"{p} likes {thing}")

        m = re.search(
            r"\b(i|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+went\s+to\s+(?:an?\s+|the\s+)?([^,\.\\n!?！？；;:：]{3,100})",
            s,
            flags=re.IGNORECASE,
        )
        if m:
            p_raw, event = m.group(1), m.group(2).strip()
            p = resolve_person(p_raw)
            p_id = add_entity(p, "Person")
            cleaned = clean_event_name(event)
            e_id = add_entity(cleaned, "Event")
            add_relation(p_id, e_id, "RELATED_TO", f"{p} went to {event}")

        m = re.search(
            r"\b(i|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+ran\s+(?:an?\s+)?([^,\.\\n!?！？；;:：]{3,100})",
            s,
            flags=re.IGNORECASE,
        )
        if m:
            p_raw, event = m.group(1), m.group(2).strip()
            p = resolve_person(p_raw)
            p_id = add_entity(p, "Person")
            cleaned = clean_event_name(event)
            e_id = add_entity(cleaned, "Event")
            add_relation(p_id, e_id, "RELATED_TO", f"{p} ran {event}")

        m = re.search(
            r"\b(i|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+painted\s+([^,\.\\n!?！？；;:：]{3,140})",
            s,
            flags=re.IGNORECASE,
        )
        if m:
            p_raw, obj = m.group(1), m.group(2).strip()
            p = resolve_person(p_raw)
            p_id = add_entity(p, "Person")
            cleaned = clean_event_name(obj)
            o_id = add_entity(cleaned, "Event")
            add_relation(p_id, o_id, "RELATED_TO", f"{p} painted {obj}")

    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\[(?P<meta>.*?)\]\s*(?P<speaker>[^:]{1,40})\s*:\s*(?P<body>.*)$", line)
        if m:
            speaker = m.group("speaker").strip()
            body = m.group("body").strip()
            meta = m.group("meta").strip()
            if meta and body:
                handle_sentence(f"{body} ({meta})", speaker=speaker)
            else:
                handle_sentence(body, speaker=speaker)
            continue
        m = re.match(r"^(?P<speaker>[^:]{1,40})\s*:\s*(?P<body>.*)$", line)
        if m:
            handle_sentence(m.group("body"), speaker=m.group("speaker"))
            continue
        handle_sentence(line)

    confidence = 0.0
    if relations:
        confidence = 0.55
    return list(entities.values()), relations, confidence
