from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional
from datetime import datetime
import hashlib
import re

from app.services.temporal_normalizer import extract_temporal_constraints, parse_duration_seconds
from app.services.quantity_parser import extract_quantities


def augment_ir_with_structured_facts(
    ir: Dict,
    text: str,
    anchor_dt: Optional[datetime] = None,
    timezone: str = "UTC",
    default_event_id: Optional[str] = None,
    default_event_name: str = "事件",
) -> Dict:
    out = deepcopy(ir or {})
    entities: List[Dict] = list(out.get("entities") or [])
    relations: List[Dict] = list(out.get("relations") or [])

    entity_ids = {e.get("id") for e in entities if e.get("id")}

    user_id = "user"
    event_id = _pick_event_id(entities)
    if not event_id and default_event_id:
        event_id = default_event_id
        if event_id not in entity_ids:
            entities.append(
                {
                    "id": event_id,
                    "name": default_event_name,
                    "type": "Event",
                    "is_user": False,
                    "confidence": 0.6,
                }
            )
            entity_ids.add(event_id)

    anchor_id = event_id or user_id
    event_entity = None
    if event_id:
        for e in entities:
            if str(e.get("id")) == event_id:
                event_entity = e
                break

    constraints = extract_temporal_constraints(text, anchor_dt=anchor_dt, timezone=timezone)
    for c in constraints:
        start = c.get("start")
        end = c.get("end")
        if not start:
            continue

        if end and end != start:
            rid = f"timerange_{str(start).replace('-', '')}_{str(end).replace('-', '')}"
            if rid not in entity_ids:
                entities.append(
                    {
                        "id": rid,
                        "name": f"{start}..{end}",
                        "type": "TimeRange",
                        "is_user": False,
                        "confidence": 1.0,
                        "start": start,
                        "end": end,
                        "timezone": c.get("timezone", timezone),
                        "precision": c.get("precision", "day"),
                    }
                )
                entity_ids.add(rid)
            relations.append(
                {
                    "source": anchor_id,
                    "target": rid,
                    "type": "HAPPENED_BETWEEN",
                    "desc": f"{anchor_id} 发生于 {start}..{end}",
                    "weight": 0.75,
                    "confidence": 0.9,
                }
            )
        else:
            tid = f"time_{str(start).replace('-', '')}"
            if tid not in entity_ids:
                entities.append(
                    {
                        "id": tid,
                        "name": start,
                        "type": "TimeExpression",
                        "is_user": False,
                        "confidence": 1.0,
                        "value": start,
                        "timezone": c.get("timezone", timezone),
                        "precision": c.get("precision", "day"),
                    }
                )
                entity_ids.add(tid)
            relations.append(
                {
                    "source": anchor_id,
                    "target": tid,
                    "type": "HAPPENED_AT",
                    "desc": f"{anchor_id} 发生于 {start}",
                    "weight": 0.8,
                    "confidence": 0.9,
                }
            )

        if event_entity is not None:
            event_entity["start_date"] = str(start)
            event_entity["end_date"] = str(end or start)
            event_entity["timezone"] = c.get("timezone", timezone)
            event_entity["time_precision"] = c.get("precision", "day")

    dur = parse_duration_seconds(text)
    if dur:
        did = f"duration_{dur}"
        if did not in entity_ids:
            entities.append(
                {
                    "id": did,
                    "name": f"{dur}s",
                    "type": "Duration",
                    "is_user": False,
                    "confidence": 1.0,
                    "seconds": int(dur),
                }
            )
            entity_ids.add(did)
        relations.append(
            {
                "source": anchor_id,
                "target": did,
                "type": "LASTED",
                "desc": f"{anchor_id} 持续 {dur} 秒",
                "weight": 0.8,
                "confidence": 0.9,
            }
        )
        if event_entity is not None:
            event_entity["duration_seconds"] = int(dur)

    cost_written = False
    for q in extract_quantities(text):
        unit = q["unit"]
        value = q["value"]
        qid = f"qty_{unit}_{int(round(value * 100))}"
        if qid not in entity_ids:
            entities.append(
                {
                    "id": qid,
                    "name": f"{value}{unit}",
                    "type": "Quantity",
                    "is_user": False,
                    "confidence": 1.0,
                    "value": float(value),
                    "unit": unit,
                }
            )
            entity_ids.add(qid)

        rel_type = "COST" if unit == "CNY" else "RELATED_TO"
        relations.append(
            {
                "source": anchor_id,
                "target": qid,
                "type": rel_type,
                "desc": f"{anchor_id} {rel_type} {value}{unit}",
                "weight": 0.7,
                "confidence": 0.9,
            }
        )
        if event_entity is not None and unit == "CNY" and not cost_written:
            event_entity["cost_value"] = float(value)
            event_entity["cost_unit"] = "CNY"
            cost_written = True

    for fact in _extract_canonical_facts(text):
        s_name = fact["subject"]
        o_name = fact["object"]
        pred = fact["predicate"].upper()
        ev = fact.get("evidence") or ""

        sid = _stable_entity_id("Person", s_name)
        oid = _stable_entity_id(fact.get("object_type") or "Attribute", o_name)

        if sid not in entity_ids:
            entities.append(
                {
                    "id": sid,
                    "name": s_name,
                    "type": "Person",
                    "is_user": False,
                    "confidence": float(fact.get("certainty") or 0.7),
                }
            )
            entity_ids.add(sid)

        if oid not in entity_ids:
            entities.append(
                {
                    "id": oid,
                    "name": o_name,
                    "type": str(fact.get("object_type") or "Attribute"),
                    "is_user": False,
                    "confidence": float(fact.get("certainty") or 0.7),
                }
            )
            entity_ids.add(oid)

        relations.append(
            {
                "source": sid,
                "target": oid,
                "type": pred,
                "desc": ev[:300],
                "weight": 0.7,
                "confidence": float(fact.get("certainty") or 0.7),
            }
        )

    out["entities"] = entities
    out["relations"] = relations
    return out


def _pick_event_id(entities: List[Dict]) -> Optional[str]:
    for e in entities:
        if e.get("type") == "Event" and e.get("id") and e.get("id") != "user":
            return str(e.get("id"))
    return None


def _stable_entity_id(prefix: str, name: str) -> str:
    n = (name or "").strip()
    h = hashlib.sha1(n.encode("utf-8")).hexdigest()[:12]
    p = re.sub(r"[^A-Za-z0-9_]+", "_", str(prefix or "Entity"))
    return f"{p.lower()}_{h}"


def _extract_canonical_facts(text: str) -> List[Dict]:
    s, body = _split_speaker(text)
    facts: List[Dict] = []

    if s and body:
        facts.extend(_extract_svo_facts(s, body, raw=text))
    facts.extend(_extract_pair_commonality_facts(body or text))
    return facts


def _split_speaker(text: str) -> tuple[Optional[str], str]:
    t = (text or "").strip()
    if ":" in t:
        left, right = t.split(":", 1)
        name = left.strip()
        if 1 <= len(name) <= 32:
            return name, right.strip()
    return None, t


def _extract_svo_facts(subject: str, body: str, raw: str) -> List[Dict]:
    s = subject.strip()
    b = body.strip()
    low = b.lower()
    out: List[Dict] = []

    m = re.search(r"\b(i am|i'm|i was|i\u2019m)\s+(?:a|an|the)?\s*([^.,;!?]+)", low, flags=re.IGNORECASE)
    if m:
        obj = body[m.start(2):m.end(2)].strip()
        if obj:
            out.append({"subject": s, "predicate": "IS", "object": obj, "object_type": "Identity", "evidence": raw, "certainty": 0.75})

    m = re.search(r"\b(i like|i love|i enjoy)\s+([^.,;!?]+)", low, flags=re.IGNORECASE)
    if m:
        obj = body[m.start(2):m.end(2)].strip()
        if obj:
            out.append({"subject": s, "predicate": "LIKES", "object": obj, "object_type": "Preference", "evidence": raw, "certainty": 0.7})

    m = re.search(r"\b(i researched|i research|i looked up|i was researching)\s+([^.,;!?]+)", low, flags=re.IGNORECASE)
    if m:
        obj = body[m.start(2):m.end(2)].strip()
        if obj:
            out.append({"subject": s, "predicate": "RESEARCHED", "object": obj, "object_type": "Topic", "evidence": raw, "certainty": 0.7})

    m = re.search(r"\b(i decided to|i plan to|i'm going to|i am going to|i want to)\s+([^.,;!?]+)", low, flags=re.IGNORECASE)
    if m:
        obj = body[m.start(2):m.end(2)].strip()
        if obj:
            out.append({"subject": s, "predicate": "PLANS_TO", "object": obj, "object_type": "Plan", "evidence": raw, "certainty": 0.65})

    return out


def _extract_pair_commonality_facts(text: str) -> List[Dict]:
    t = (text or "").strip()
    out: List[Dict] = []
    m = re.search(r"\b([A-Z][a-z]{1,20})\s+and\s+([A-Z][a-z]{1,20})\b(.{0,120})\b(both|each)\b(.{0,120})", t)
    if not m:
        return out
    a = m.group(1).strip()
    b = m.group(2).strip()
    rest = (m.group(0) or "").strip()
    trait = (m.group(5) or "").strip(" .,:;!-")
    if trait:
        out.append({"subject": a, "predicate": "SHARES", "object": trait, "object_type": "Trait", "evidence": rest, "certainty": 0.6})
        out.append({"subject": b, "predicate": "SHARES", "object": trait, "object_type": "Trait", "evidence": rest, "certainty": 0.6})
    return out
