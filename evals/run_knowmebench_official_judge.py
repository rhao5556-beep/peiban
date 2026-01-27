import argparse
import json
import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


_PROMPT_SPLIT_RE = re.compile(r"^# type\s+(.+)$", flags=re.MULTILINE)


def _load_env_local() -> None:
    env_path = Path(__file__).parent / ".env.local"
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
        return
    except Exception:
        pass

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            os.environ[k] = v


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _parse_prompt_file(prompt_path: Path) -> Dict[str, str]:
    content = prompt_path.read_text(encoding="utf-8")
    sections = _PROMPT_SPLIT_RE.split(content)
    prompts: Dict[str, str] = {}
    for i in range(1, len(sections), 2):
        task_types_raw = (sections[i] or "").strip()
        prompt_content = (sections[i + 1] or "").strip()
        task_types = [t.strip() for t in re.split(r"[、,]", task_types_raw) if t.strip()]
        for t in task_types:
            prompts[t] = prompt_content
    return prompts


def _build_prompt(prompt_template: str, item: Dict[str, Any]) -> str:
    user_question = item.get("question", "")
    ref_answer = item.get("reference_answer", "")
    model_ans = item.get("model_answer", "")
    return (
        str(prompt_template)
        .replace("{{question}}", str(user_question))
        .replace("{{reference_answer}}", str(ref_answer))
        .replace("{{model_answer}}", str(model_ans))
    )


def _call_judge(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout_s: float,
) -> Tuple[Optional[int], str, Optional[str]]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an impartial judge. Return a JSON object with keys: "
                    "score (integer 0-5) and reasoning (string)."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    last_error: Optional[str] = None
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
            if resp.status_code >= 400:
                raise RuntimeError(f"{resp.status_code} {resp.text}")
            data = resp.json()
            text = (
                (data.get("choices") or [{}])[0].get("message", {}).get("content", "")  # type: ignore[union-attr]
            )
            obj = None
            try:
                obj = json.loads(text)
            except Exception:
                obj = _extract_first_json_object(str(text))
            if not isinstance(obj, dict):
                raise RuntimeError("judge_returned_non_json")
            score = obj.get("score")
            reasoning = obj.get("reasoning", "")
            try:
                score_int = int(score)
            except Exception:
                score_int = None
            if score_int is None or score_int < 0 or score_int > 5:
                raise RuntimeError(f"invalid_score: {score!r}")
            return score_int, str(reasoning), None
        except Exception as e:
            last_error = f"{e.__class__.__name__}: {e}"
            if attempt == 0:
                payload.pop("response_format", None)
                time.sleep(0.2)
                continue
            break
    return None, "", last_error


def main() -> None:
    _load_env_local()

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--input_file", default="")
    parser.add_argument("--output_file", default="")
    parser.add_argument("--judge_model", default=os.environ.get("AFFINITY_EVAL_JUDGE_MODEL", "gpt-4o"))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout_s", type=float, default=float(os.environ.get("AFFINITY_EVAL_OPENAI_TIMEOUT_S", "60")))
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    input_file = Path(args.input_file) if args.input_file else (input_dir / "merged_for_official_eval.json")
    output_file = Path(args.output_file) if args.output_file else (input_dir / "judge_results.json")

    prompt_path = Path(__file__).resolve().parents[1] / "external" / "KnowMeBench" / "evaluate" / "evaluate prompt.md"
    prompts_map = _parse_prompt_file(prompt_path)

    api_key = os.environ.get("AFFINITY_EVAL_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    base_url = os.environ.get("AFFINITY_EVAL_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
    if not api_key or not base_url:
        raise RuntimeError("missing_api_config: set AFFINITY_EVAL_OPENAI_API_KEY and AFFINITY_EVAL_OPENAI_BASE_URL")

    data: List[Dict[str, Any]] = _load_json(input_file)
    results: List[Dict[str, Any]] = [None] * len(data)  # type: ignore[list-item]

    def _run_one(idx: int, item: Dict[str, Any]) -> Dict[str, Any]:
        task_type = item.get("task_type")
        if not task_type or task_type not in prompts_map:
            return {
                "id": item.get("id"),
                "task_type": task_type,
                "score": None,
                "reasoning": "Task type not found in prompt file",
                "status": "skipped",
            }
        prompt = _build_prompt(prompts_map[str(task_type)], item)
        score, reasoning, err = _call_judge(
            prompt=prompt,
            api_key=api_key,
            base_url=base_url,
            model=str(args.judge_model),
            timeout_s=float(args.timeout_s),
        )
        if err:
            return {
                "id": item.get("id"),
                "task_type": task_type,
                "score": 0,
                "reasoning": f"Evaluation Error: {err}",
                "status": "error",
            }
        return {
            "id": item.get("id"),
            "task_type": task_type,
            "score": score,
            "reasoning": reasoning,
            "status": "success",
        }

    done = 0
    total_n = len(data)
    with ThreadPoolExecutor(max_workers=max(1, int(args.concurrency))) as ex:
        fut_to_idx = {ex.submit(_run_one, idx, item): idx for idx, item in enumerate(data)}
        pending = set(fut_to_idx.keys())
        while pending:
            done_set, pending = wait(pending, timeout=15.0, return_when=FIRST_COMPLETED)
            for fut in done_set:
                idx = fut_to_idx[fut]
                results[idx] = fut.result()
                done += 1
                if done <= 5 or done % 10 == 0 or done == total_n:
                    item_id = results[idx].get("id") if results[idx] else None
                    print(f"[{done}/{total_n}] id={item_id}", flush=True)

    valid_scores = [
        r.get("score")
        for r in results
        if isinstance(r, dict) and r.get("status") == "success" and isinstance(r.get("score"), (int, float))
    ]
    avg_score = (sum(valid_scores) / len(valid_scores)) if valid_scores else 0.0

    output_data = {
        "meta": {
            "judge_model": str(args.judge_model),
            "total_items": len(data),
            "evaluated_items": len(valid_scores),
            "average_score": round(float(avg_score), 4),
        },
        "details": results,
    }
    output_file.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output_file))


if __name__ == "__main__":
    main()
