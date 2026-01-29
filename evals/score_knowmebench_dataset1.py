import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


_NORM_RE = re.compile(r"[^a-z0-9]+", re.IGNORECASE)


def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = _NORM_RE.sub("", s)
    return s


def _extract_ints(s: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", s or "")]


def _try_parse_jsonish(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        return json.loads((s or "").replace("'", "\""))
    except Exception:
        return None


def _offline_heuristic_correct(task_type: str, reference: str, prediction: str) -> bool:
    t = (task_type or "").strip().lower()
    r = (reference or "").strip()
    p = (prediction or "").strip()
    nr = _norm_text(r)
    np = _norm_text(p)
    if not nr:
        return False

    if "adversarial" in t and "abstention" in t:
        abstain_markers = [
            "i dont know",
            "i don't know",
            "insufficient",
            "not mentioned",
            "does not mention",
            "cannot determine",
            "no information",
            "unknown",
        ]
        low = (p or "").lower()
        return any(m in low for m in abstain_markers)

    if "temporal" in t and "reasoning" in t:
        ref_ints = _extract_ints(r)
        pred_ints = _extract_ints(p)
        if not ref_ints:
            return False
        return all(x in pred_ints for x in ref_ints)

    if "logical" in t and "ordering" in t:
        parsed = _try_parse_jsonish(r)
        events: List[str] = []
        if isinstance(parsed, list):
            for it in parsed:
                if isinstance(it, dict) and it.get("event"):
                    events.append(str(it["event"]))
        if events:
            hit = 0
            low = (p or "").lower()
            for ev in events:
                if _norm_text(ev) and _norm_text(ev) in _norm_text(low):
                    hit += 1
            return hit >= max(1, min(2, len(events)))
        return nr in np or np in nr

    if nr in np or np in nr:
        return True

    ref_ints = _extract_ints(r)
    pred_ints = _extract_ints(p)
    if ref_ints and all(x in pred_ints for x in ref_ints):
        return True
    return False


def _call_llm_judge(
    task_type: str,
    question: str,
    reference_answer: str,
    model_answer: str,
    api_key: str,
    api_base: str,
    model: str,
    timeout_s: float,
) -> Tuple[bool, float, str]:
    prompt = f"""You are an expert evaluator for long-term memory systems. Judge whether the model's answer is correct compared to the reference answer.

Task Type: {task_type}
Question: {question}

Reference Answer: {reference_answer}
Model Answer: {model_answer}

Guidelines:
- Be strict but fair.
- Paraphrasing is acceptable if meaning is preserved.
- If the model answer is empty or refuses without matching the reference, mark incorrect.

Respond in JSON:
{{
  "correct": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    resp = requests.post(
        f"{api_base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
            "max_tokens": 400,
        },
        timeout=float(timeout_s),
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    content = (content or "").strip()
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


@dataclass(frozen=True)
class ScoredItem:
    qid: int
    task_type: str
    correct: bool
    confidence: float
    reference: str
    prediction: str
    reasoning: str
    had_error: bool
    empty_prediction: bool


def score_items(
    items: List[Dict[str, Any]],
    use_llm: bool,
    api_key: Optional[str],
    api_base: str,
    model: str,
    rate_limit_delay: float,
    timeout_s: float,
    max_items: int,
    fallback_to_exact_match_on_llm_error: bool,
    offline_mode: str,
) -> Tuple[Dict[str, Any], List[ScoredItem]]:
    if max_items > 0:
        items = items[:max_items]

    scored: List[ScoredItem] = []

    for i, it in enumerate(items):
        qid = int(it.get("id") or 0)
        task_type = str(it.get("task_type") or "")
        question = str(it.get("question") or "")
        reference = str(it.get("reference_answer") or "")
        prediction = str(it.get("model_answer") or "")
        meta = it.get("meta") or {}
        had_error = bool(meta.get("error"))
        empty_prediction = not prediction.strip()

        if use_llm:
            if not api_key:
                if fallback_to_exact_match_on_llm_error:
                    correct = bool(reference.strip()) and reference.strip().lower() == prediction.strip().lower()
                    confidence = 1.0 if correct else 0.0
                    reasoning = "fallback_no_api_key_exact_match"
                else:
                    raise RuntimeError("OPENAI_API_KEY is required when use_llm is enabled")
            else:
                correct = False
                confidence = 0.0
                reasoning = ""
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        correct, confidence, reasoning = _call_llm_judge(
                            task_type=task_type,
                            question=question,
                            reference_answer=reference,
                            model_answer=prediction,
                            api_key=api_key,
                            api_base=api_base,
                            model=model,
                            timeout_s=timeout_s,
                        )
                        break
                    except Exception as e:
                        last_error = e
                        if attempt >= 2:
                            if fallback_to_exact_match_on_llm_error:
                                correct = bool(reference.strip()) and reference.strip().lower() == prediction.strip().lower()
                                confidence = 1.0 if correct else 0.0
                                reasoning = f"fallback_llm_error_exact_match:{e.__class__.__name__}"
                                break
                            raise
                        time.sleep(rate_limit_delay or 0.1)
        else:
            mode = (offline_mode or "exact_match").strip().lower()
            if mode == "heuristic":
                correct = _offline_heuristic_correct(task_type, reference, prediction)
                confidence = 1.0 if correct else 0.0
                reasoning = "offline_heuristic"
            else:
                correct = bool(reference.strip()) and reference.strip().lower() == prediction.strip().lower()
                confidence = 1.0 if correct else 0.0
                reasoning = "exact_match"

        scored.append(
            ScoredItem(
                qid=qid,
                task_type=task_type,
                correct=bool(correct),
                confidence=float(confidence),
                reference=reference,
                prediction=prediction,
                reasoning=reasoning,
                had_error=had_error,
                empty_prediction=empty_prediction,
            )
        )

        if use_llm and i > 0 and rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

    total = len(scored)
    correct_n = sum(1 for s in scored if s.correct)
    error_n = sum(1 for s in scored if s.had_error)
    empty_n = sum(1 for s in scored if s.empty_prediction)
    avg_conf = sum(s.confidence for s in scored) / total if total else 0.0

    by_task: Dict[str, Dict[str, Any]] = {}
    for s in scored:
        t = s.task_type or "unknown"
        d = by_task.setdefault(t, {"total": 0, "correct": 0, "accuracy": 0.0})
        d["total"] += 1
        d["correct"] += 1 if s.correct else 0
    for t, d in by_task.items():
        d["accuracy"] = (d["correct"] / d["total"]) if d["total"] else 0.0

    summary = {
        "total": total,
        "correct": correct_n,
        "accuracy": (correct_n / total) if total else 0.0,
        "avg_confidence": avg_conf,
        "error_items": error_n,
        "empty_predictions": empty_n,
        "scoring_method": "llm_judge" if use_llm else "exact_match",
        "by_task_type": dict(sorted(by_task.items(), key=lambda kv: kv[0])),
    }

    return summary, scored


def main() -> None:
    p = argparse.ArgumentParser(description="Score KnowMeBench dataset1 outputs")
    p.add_argument("--in_path", required=True, help="Path to merged_for_official_eval.json")
    p.add_argument("--out_summary_path", default="", help="Path to save scoring summary")
    p.add_argument("--failures_out_path", default="", help="Path to save failures")
    p.add_argument("--detailed_out_path", default="", help="Path to save detailed scores")
    p.add_argument("--use_llm", action="store_true", default=True, help="Use LLM judge")
    p.add_argument("--no_llm", action="store_true", help="Disable LLM judge (exact match only)")
    p.add_argument("--api_key", default=os.environ.get("EVAL_JUDGE_API_KEY") or os.environ.get("OPENAI_API_KEY"), help="API key")
    p.add_argument(
        "--api_base",
        default=os.environ.get("EVAL_JUDGE_API_BASE") or os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1"),
        help="API base URL",
    )
    p.add_argument("--model", default=os.environ.get("EVAL_JUDGE_MODEL") or os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3"), help="Judge model")
    p.add_argument("--rate_limit_delay", type=float, default=0.1, help="Delay between API calls")
    p.add_argument("--timeout_s", type=float, default=60.0, help="Timeout for each LLM judge call")
    p.add_argument("--max_items", type=int, default=0, help="Only score first N items (0=all)")
    p.add_argument("--fallback_to_exact_match_on_llm_error", action="store_true", default=True)
    p.add_argument("--offline_mode", choices=["exact_match", "heuristic"], default="heuristic")
    args = p.parse_args()

    use_llm = args.use_llm and not args.no_llm

    in_path = Path(args.in_path)
    items = _load_json(in_path)
    if not isinstance(items, list):
        raise RuntimeError("in_path must be a JSON list")

    print(f"Scoring {len(items) if args.max_items <= 0 else min(len(items), args.max_items)} items...")
    print(f"Scoring method: {'LLM Judge' if use_llm else 'Exact Match'}")
    if use_llm:
        print(f"Judge model: {args.model}")

    summary, scored = score_items(
        items=items,
        use_llm=use_llm,
        api_key=args.api_key,
        api_base=args.api_base,
        model=args.model,
        rate_limit_delay=args.rate_limit_delay,
        timeout_s=float(args.timeout_s),
        max_items=int(args.max_items),
        fallback_to_exact_match_on_llm_error=bool(args.fallback_to_exact_match_on_llm_error),
        offline_mode=str(args.offline_mode),
    )

    print("\n" + "=" * 60)
    print("SCORING SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.out_summary_path:
        outp = Path(args.out_summary_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.failures_out_path:
        failures = [
            {
                "id": s.qid,
                "task_type": s.task_type,
                "reference_answer": s.reference,
                "model_answer": s.prediction,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "had_error": s.had_error,
                "empty_prediction": s.empty_prediction,
            }
            for s in scored
            if not s.correct
        ]
        fp = Path(args.failures_out_path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.detailed_out_path:
        detailed = [
            {
                "id": s.qid,
                "task_type": s.task_type,
                "correct": s.correct,
                "confidence": s.confidence,
                "reference_answer": s.reference,
                "model_answer": s.prediction,
                "reasoning": s.reasoning,
                "had_error": s.had_error,
                "empty_prediction": s.empty_prediction,
            }
            for s in scored
        ]
        dp = Path(args.detailed_out_path)
        dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_text(json.dumps(detailed, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
