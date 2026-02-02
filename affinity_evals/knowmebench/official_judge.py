import argparse
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

try:
    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / "evals" / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass


def _first_env(*names: str) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _sleep_backoff(attempt: int, cap_s: float) -> None:
    base = 1.6 ** attempt
    jitter = random.random() * 0.6
    time.sleep(min(float(cap_s), base + jitter))


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_items(input_dir: Path) -> List[Dict[str, Any]]:
    merged = input_dir / "merged_for_official_eval.json"
    if merged.exists():
        data = _load_json(merged)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

    items: List[Dict[str, Any]] = []
    for p in sorted(input_dir.glob("knowmebench.dataset1.*.model_outputs.json")):
        data = _load_json(p)
        if isinstance(data, list):
            items.extend([x for x in data if isinstance(x, dict)])
    return items


def _extract_fields(it: Dict[str, Any]) -> Tuple[int, str, str, str]:
    qid = int(it.get("id") or 0)
    task_type = str(it.get("task_type") or "")
    question = str(it.get("question") or "")
    reference = str(it.get("reference_answer") or "")
    model_answer = str(it.get("model_answer") or "")
    prompt = (
        "You are a strict evaluator for long-term memory tasks.\n"
        "Score the model answer against the reference on a 0-5 integer scale.\n\n"
        "Rubric:\n"
        "- 5: Fully correct, no fabrication, matches key facts.\n"
        "- 3: Partially correct; minor mistakes or missing details.\n"
        "- 1: Mostly incorrect or major mistakes.\n"
        "- 0: Fabricated or contradicts the reference.\n\n"
        f"Task Type: {task_type}\n"
        f"Question: {question}\n"
        f"Reference Answer: {reference}\n"
        f"Model Answer: {model_answer}\n\n"
        'Return JSON only: {"score": 0-5, "reasoning": "short"}\n'
    )
    return qid, task_type, prompt, reference


def _parse_judge_json(text: str) -> Tuple[int, str]:
    t = (text or "").strip()
    if t.startswith("```json"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()
    try:
        obj = json.loads(t)
    except Exception:
        return 0, f"judge_non_json: {t[:200]}"
    score = obj.get("score")
    reasoning = obj.get("reasoning")
    try:
        score_i = int(score)
    except Exception:
        score_i = 0
    if score_i < 0:
        score_i = 0
    if score_i > 5:
        score_i = 5
    return score_i, str(reasoning or "").strip()


_thread_local = threading.local()


def _get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


@dataclass(frozen=True)
class JudgeConfig:
    api_key: str
    api_base: str
    model: str
    timeout_s: float


def _call_judge(cfg: JudgeConfig, prompt: str) -> Tuple[int, str]:
    url = urljoin(cfg.api_base.rstrip("/") + "/", "chat/completions")
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 300,
    }
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            s = _get_session()
            resp = s.post(
                url,
                headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=float(cfg.timeout_s),
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _parse_judge_json(str(content))
        except Exception as e:
            last_error = e
            if attempt >= 7:
                break
            _sleep_backoff(attempt, cap_s=25.0)
    return 0, f"judge_error: {last_error}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", required=True)
    p.add_argument("--output_file", required=True)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--timeout_s", type=float, default=30.0)
    p.add_argument("--api_key", default=_first_env("AFFINITY_EVAL_OPENAI_API_KEY", "OPENAI_API_KEY"))
    p.add_argument(
        "--api_base",
        default=_first_env("AFFINITY_EVAL_OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_BASE_URL"),
    )
    p.add_argument("--judge_model", default=_first_env("AFFINITY_EVAL_JUDGE_MODEL", "OPENAI_MODEL"))
    p.add_argument("--force", action="store_true", default=False)
    args = p.parse_args()

    input_dir = Path(args.input_dir)
    out_path = Path(args.output_file)

    if out_path.exists() and not args.force:
        print(f"SKIP: judge_results_exists: {out_path}")
        return

    if not args.api_key or not args.api_base or not args.judge_model:
        raise SystemExit("missing judge config: api_key/api_base/judge_model")

    items = _find_items(input_dir)
    total = len(items)
    if total == 0:
        raise SystemExit(f"no items to judge in: {input_dir}")

    print(f"Judge start: items={total} concurrency={int(args.concurrency)} model={args.judge_model}", flush=True)
    cfg = JudgeConfig(
        api_key=str(args.api_key),
        api_base=str(args.api_base),
        model=str(args.judge_model),
        timeout_s=float(args.timeout_s),
    )

    details: List[Dict[str, Any]] = []
    score_sum = 0
    evaluated = 0

    def _run_one(it: Dict[str, Any]) -> Dict[str, Any]:
        qid = int(it.get("id") or 0)
        task_type = str(it.get("task_type") or "")
        _, _, prompt, _ = _extract_fields(it)
        score, reasoning = _call_judge(cfg, prompt=prompt)
        status = "ok" if reasoning and not reasoning.startswith("judge_error") else "err"
        return {"id": qid, "task_type": task_type, "score": int(score), "reasoning": reasoning, "status": status}

    with ThreadPoolExecutor(max_workers=max(1, int(args.concurrency))) as ex:
        futs = [ex.submit(_run_one, it) for it in items]
        for i, fut in enumerate(as_completed(futs), start=1):
            r = fut.result()
            details.append(r)
            evaluated += 1
            score_sum += int(r.get("score") or 0)
            if i <= 5 or i % 5 == 0 or i == total:
                print(f"[{i}/{total}] id={r.get('id')} score={r.get('score')} status={r.get('status')}", flush=True)

    details.sort(key=lambda x: (str(x.get("task_type") or ""), int(x.get("id") or 0)))
    avg_score = (score_sum / evaluated) if evaluated else 0.0
    out = {
        "meta": {
            "judge_model": str(args.judge_model),
            "total_items": total,
            "evaluated_items": evaluated,
            "average_score": avg_score,
        },
        "details": details,
    }
    _dump_json(out_path, out)
    print(f"Wrote: {out_path}", flush=True)


if __name__ == "__main__":
    main()
