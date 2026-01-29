"""
LoCoMo LLM-based Scoring Script

使用真实 LLM 对 LoCoMo 评测结果进行智能评分
支持语义理解和推理评估
"""
import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Load .env.local if exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use system env vars


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


# Category definitions from LoCoMo paper
CATEGORY_NAMES = {
    1: "Factual Recall",
    2: "Temporal Understanding",
    3: "Reasoning & Inference",
    4: "Detailed Understanding",
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


def _exact_match_score(reference: str, prediction: str, category: Optional[int]) -> bool:
    """Simple exact match scoring (fallback)"""
    if category == 2:  # Temporal
        ref_iso = _to_iso_date(reference)
        pred_iso = _to_iso_date(prediction)
        if ref_iso and pred_iso:
            return ref_iso == pred_iso
    
    ref_n = _normalize_text(reference)
    pred_n = _normalize_text(prediction)
    return bool(ref_n) and ref_n == pred_n


def _call_llm_judge(
    question: str,
    reference_answer: str,
    model_answer: str,
    category: Optional[int],
    api_key: str,
    api_base: str,
    model: str,
    timeout_s: float,
) -> Tuple[bool, float, str]:
    """
    Call LLM to judge if the model answer is correct
    
    Returns:
        (is_correct, confidence, reasoning)
    """
    category_name = CATEGORY_NAMES.get(category, "Unknown")
    
    prompt = f"""You are an expert evaluator for long-term memory systems. Your task is to judge if a model's answer is correct compared to the reference answer.

Question Type: {category_name} (Category {category})
Question: {question}

Reference Answer: {reference_answer}
Model Answer: {model_answer}

Evaluation Guidelines:
- For Factual Recall (Category 1): Check if key facts match, allow for paraphrasing
- For Temporal Understanding (Category 2): Check if dates/times are equivalent (e.g., "7 May 2023" = "May 7, 2023")
- For Reasoning & Inference (Category 3): Check if the reasoning is sound and conclusion matches
- For Detailed Understanding (Category 4): Check if the answer captures the essential details

Respond in JSON format:
{{
    "correct": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

Be strict but fair. Minor paraphrasing is acceptable if the meaning is preserved."""

    try:
        response = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return only a valid JSON object. No markdown, no extra keys, no prose.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 500,
            },
            timeout=float(timeout_s),
        )
        response.raise_for_status()
        
        content = response.json()["choices"][0]["message"]["content"]
        
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                result = json.loads(content[start : end + 1])
            else:
                raise
        return (
            bool(result.get("correct", False)),
            float(result.get("confidence", 0.0)),
            str(result.get("reasoning", "")),
        )
    
    except Exception as e:
        print(f"Warning: LLM judge failed: {e}")
        # Fallback to exact match
        exact = _exact_match_score(reference_answer, model_answer, category)
        return exact, 1.0 if exact else 0.0, f"Fallback to exact match due to error: {e}"


@dataclass(frozen=True)
class ScoredItem:
    qid: int
    task_type: str
    category: Optional[int]
    correct: bool
    confidence: float
    reference: str
    prediction: str
    reasoning: str
    exact_match: bool


def score_outputs_with_llm(
    items: List[Dict[str, Any]],
    use_llm: bool = True,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    model: Optional[str] = None,
    rate_limit_delay: float = 0.1,
    timeout_s: float = 30.0,
) -> Tuple[Dict[str, Any], List[ScoredItem]]:
    """
    Score model outputs using LLM judge
    
    Args:
        items: List of evaluation items
        use_llm: Whether to use LLM judge (if False, use exact match only)
        api_key: OpenAI-compatible API key
        api_base: API base URL
        model: Model name for judging
        rate_limit_delay: Delay between API calls (seconds)
    """
    scored: List[ScoredItem] = []
    
    for i, it in enumerate(items):
        qid = int(it.get("id") or 0)
        meta = it.get("meta") or {}
        task_type_raw = it.get("task_type") or meta.get("task_type") or ""
        task_type = str(task_type_raw).strip() or "unknown"
        question = str(it.get("question") or "")
        ref = str(it.get("reference_answer") or "")
        pred = str(it.get("model_answer") or "")
        cat = it.get("category")
        if not isinstance(cat, int):
            cat = meta.get("category")
        category = int(cat) if isinstance(cat, int) else None
        
        # Always compute exact match
        exact_match = _exact_match_score(ref, pred, category)
        
        # Use LLM judge if enabled
        if use_llm and api_key and api_base and model:
            try:
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        correct, confidence, reasoning = _call_llm_judge(
                            question=question,
                            reference_answer=ref,
                            model_answer=pred,
                            category=category,
                            api_key=api_key,
                            api_base=api_base,
                            model=model,
                            timeout_s=timeout_s,
                        )
                        break
                    except Exception as e:
                        last_error = e
                        if attempt >= 2:
                            raise
                        time.sleep(rate_limit_delay or 0.1)
                if i > 0 and rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)
            except Exception as e:
                print(f"Error judging item {qid}: {e}")
                correct = exact_match
                confidence = 1.0 if exact_match else 0.0
                reasoning = f"Fallback to exact match due to error"
        else:
            correct = exact_match
            confidence = 1.0 if exact_match else 0.0
            reasoning = "Exact match scoring"
        
        scored.append(
            ScoredItem(
                qid=qid,
                task_type=task_type,
                category=category,
                correct=correct,
                confidence=confidence,
                reference=ref,
                prediction=pred,
                reasoning=reasoning,
                exact_match=exact_match,
            )
        )
        
        if (i + 1) % 10 == 0:
            print(f"Scored {i + 1}/{len(items)} items...")
    
    # Compute statistics
    total = len(scored)
    correct_n = sum(1 for s in scored if s.correct)
    exact_match_n = sum(1 for s in scored if s.exact_match)
    accuracy = (correct_n / total) if total else 0.0
    exact_match_acc = (exact_match_n / total) if total else 0.0
    avg_confidence = (sum(s.confidence for s in scored) / total) if total else 0.0
    
    by_task: Dict[str, Dict[str, Any]] = {}
    by_cat: Dict[str, Dict[str, Any]] = {}
    
    for s in scored:
        t = s.task_type or "unknown"
        by_task.setdefault(t, {"total": 0, "correct": 0, "exact_match": 0, "confidence_sum": 0.0})
        by_task[t]["total"] += 1
        by_task[t]["correct"] += 1 if s.correct else 0
        by_task[t]["exact_match"] += 1 if s.exact_match else 0
        by_task[t]["confidence_sum"] += s.confidence
        
        c = str(s.category) if s.category is not None else "unknown"
        cat_name = CATEGORY_NAMES.get(s.category, "Unknown") if s.category is not None else "Unknown"
        by_cat.setdefault(c, {
            "category_name": cat_name,
            "total": 0,
            "correct": 0,
            "exact_match": 0,
            "confidence_sum": 0.0
        })
        by_cat[c]["total"] += 1
        by_cat[c]["correct"] += 1 if s.correct else 0
        by_cat[c]["exact_match"] += 1 if s.exact_match else 0
        by_cat[c]["confidence_sum"] += s.confidence
    
    for d in by_task.values():
        d["accuracy"] = (d["correct"] / d["total"]) if d["total"] else 0.0
        d["exact_match_accuracy"] = (d["exact_match"] / d["total"]) if d["total"] else 0.0
        d["avg_confidence"] = (d["confidence_sum"] / d["total"]) if d["total"] else 0.0
        del d["confidence_sum"]
    
    for d in by_cat.values():
        d["accuracy"] = (d["correct"] / d["total"]) if d["total"] else 0.0
        d["exact_match_accuracy"] = (d["exact_match"] / d["total"]) if d["total"] else 0.0
        d["avg_confidence"] = (d["confidence_sum"] / d["total"]) if d["total"] else 0.0
        del d["confidence_sum"]
    
    summary = {
        "total": total,
        "correct": correct_n,
        "exact_match": exact_match_n,
        "accuracy": accuracy,
        "exact_match_accuracy": exact_match_acc,
        "avg_confidence": avg_confidence,
        "scoring_method": "llm_judge" if use_llm else "exact_match",
        "by_task_type": dict(sorted(by_task.items(), key=lambda kv: kv[0])),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: kv[0])),
    }
    
    return summary, scored


def main() -> None:
    p = argparse.ArgumentParser(description="Score LoCoMo outputs using LLM judge")
    p.add_argument("--in_path", required=True, help="Path to model outputs JSON")
    p.add_argument("--out_path", default="", help="Path to save scoring summary")
    p.add_argument("--failures_out_path", default="", help="Path to save failures")
    p.add_argument("--detailed_out_path", default="", help="Path to save detailed scores")
    p.add_argument("--use_llm", action="store_true", default=True, help="Use LLM judge")
    p.add_argument("--no_llm", action="store_true", help="Disable LLM judge (exact match only)")
    p.add_argument("--api_key", default=os.environ.get("EVAL_JUDGE_API_KEY") or os.environ.get("OPENAI_API_KEY"), help="API key")
    p.add_argument("--api_base", default=os.environ.get("EVAL_JUDGE_API_BASE") or os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1"), help="API base URL")
    p.add_argument("--model", default=os.environ.get("EVAL_JUDGE_MODEL") or os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3"), help="Judge model")
    p.add_argument("--rate_limit_delay", type=float, default=0.1, help="Delay between API calls")
    p.add_argument("--timeout_s", type=float, default=30.0, help="Timeout for each LLM judge call")
    args = p.parse_args()
    
    use_llm = args.use_llm and not args.no_llm
    
    if use_llm and not args.api_key:
        print("Warning: No API key provided, falling back to exact match scoring")
        use_llm = False
    
    in_path = Path(args.in_path)
    items = _load_json(in_path)
    if not isinstance(items, list):
        raise RuntimeError("in_path must be a JSON list of model outputs")
    
    print(f"Scoring {len(items)} items...")
    print(f"Scoring method: {'LLM Judge' if use_llm else 'Exact Match'}")
    if use_llm:
        print(f"Judge model: {args.model}")
    
    summary, scored = score_outputs_with_llm(
        items=items,
        use_llm=use_llm,
        api_key=args.api_key,
        api_base=args.api_base,
        model=args.model,
        rate_limit_delay=args.rate_limit_delay,
        timeout_s=float(args.timeout_s),
    )
    
    print("\n" + "="*60)
    print("SCORING SUMMARY")
    print("="*60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    
    if args.out_path:
        out_path = Path(args.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSummary saved to: {out_path}")
    
    if args.failures_out_path:
        failures = [
            {
                "id": s.qid,
                "task_type": s.task_type,
                "category": s.category,
                "category_name": CATEGORY_NAMES.get(s.category, "Unknown") if s.category else "Unknown",
                "reference_answer": s.reference,
                "model_answer": s.prediction,
                "exact_match": s.exact_match,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
            }
            for s in scored
            if not s.correct
        ]
        fp = Path(args.failures_out_path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Failures saved to: {fp}")
    
    if args.detailed_out_path:
        detailed = [
            {
                "id": s.qid,
                "task_type": s.task_type,
                "category": s.category,
                "category_name": CATEGORY_NAMES.get(s.category, "Unknown") if s.category else "Unknown",
                "correct": s.correct,
                "exact_match": s.exact_match,
                "confidence": s.confidence,
                "reference_answer": s.reference,
                "model_answer": s.prediction,
                "reasoning": s.reasoning,
            }
            for s in scored
        ]
        dp = Path(args.detailed_out_path)
        dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_text(json.dumps(detailed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Detailed scores saved to: {dp}")


if __name__ == "__main__":
    main()
