import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\"'`，,。．\.！!？\?\(\)\[\]\{\}:：;；\-—_]+")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")
_MDY_RE = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b")


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


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_text(s: str) -> str:
    x = (s or "").strip().lower()
    x = _PUNCT_RE.sub(" ", x)
    x = _WS_RE.sub(" ", x).strip()
    return x


def _to_iso_date(s: str) -> Optional[str]:
    t = (s or "").strip()
    m = _ISO_DATE_RE.search(t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    m = _DMY_RE.search(t)
    if m:
        day = int(m.group(1))
        month = MONTHS.get(m.group(2).strip().lower())
        year = int(m.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"

    m = _MDY_RE.search(t)
    if m:
        month = MONTHS.get(m.group(1).strip().lower())
        day = int(m.group(2))
        year = int(m.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def _normalize_answer_for_scoring(answer: str, category: Optional[int]) -> str:
    if category == 2:
        iso = _to_iso_date(answer)
        if iso:
            return iso
    return _normalize_text(answer)


@dataclass(frozen=True)
class ScoredItem:
    qid: int
    task_type: str
    category: Optional[int]
    correct: bool
    reference: str
    prediction: str


def score_outputs(items: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[ScoredItem]]:
    scored: List[ScoredItem] = []
    for it in items:
        qid = int(it.get("id") or 0)
        task_type = str(it.get("task_type") or "")
        ref = str(it.get("reference_answer") or "")
        pred = str(it.get("model_answer") or "")
        meta = it.get("meta") or {}
        cat = meta.get("category")
        category = int(cat) if isinstance(cat, int) else None

        ref_n = _normalize_answer_for_scoring(ref, category)
        pred_n = _normalize_answer_for_scoring(pred, category)
        correct = bool(ref_n) and ref_n == pred_n

        scored.append(
            ScoredItem(
                qid=qid,
                task_type=task_type,
                category=category,
                correct=correct,
                reference=ref,
                prediction=pred,
            )
        )

    total = len(scored)
    correct_n = sum(1 for s in scored if s.correct)
    accuracy = (correct_n / total) if total else 0.0

    by_task: Dict[str, Dict[str, Any]] = {}
    by_cat: Dict[str, Dict[str, Any]] = {}
    for s in scored:
        t = s.task_type or "unknown"
        by_task.setdefault(t, {"total": 0, "correct": 0})
        by_task[t]["total"] += 1
        by_task[t]["correct"] += 1 if s.correct else 0

        c = str(s.category) if s.category is not None else "unknown"
        by_cat.setdefault(c, {"total": 0, "correct": 0})
        by_cat[c]["total"] += 1
        by_cat[c]["correct"] += 1 if s.correct else 0

    for d in by_task.values():
        d["accuracy"] = (d["correct"] / d["total"]) if d["total"] else 0.0
    for d in by_cat.values():
        d["accuracy"] = (d["correct"] / d["total"]) if d["total"] else 0.0

    summary = {
        "total": total,
        "correct": correct_n,
        "accuracy": accuracy,
        "by_task_type": dict(sorted(by_task.items(), key=lambda kv: kv[0])),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: kv[0])),
    }
    return summary, scored


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in_path", required=True)
    p.add_argument("--out_path", default="")
    p.add_argument("--failures_out_path", default="")
    args = p.parse_args()

    in_path = Path(args.in_path)
    items = _load_json(in_path)
    if not isinstance(items, list):
        raise RuntimeError("in_path must be a JSON list of model outputs")

    summary, scored = score_outputs(items)

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.out_path:
        out_path = Path(args.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.failures_out_path:
        failures = [
            {
                "id": s.qid,
                "task_type": s.task_type,
                "category": s.category,
                "reference_answer": s.reference,
                "model_answer": s.prediction,
            }
            for s in scored
            if not s.correct
        ]
        fp = Path(args.failures_out_path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

