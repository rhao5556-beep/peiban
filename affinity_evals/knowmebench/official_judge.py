import argparse
import json
import os
import random
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parents[2] / "evals" / ".env.local"
    if _env_path.exists():
        load_dotenv(_env_path)
except Exception:
    pass


_TYPE_RE = re.compile(r"^\s*#\s*type\s+(?P<types>.+?)\s*$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sleep_backoff(attempt: int, cap_s: float) -> None:
    base = 1.6 ** attempt
    jitter = random.random() * 0.4
    time.sleep(min(cap_s, base + jitter))


def _split_types(s: str) -> List[str]:
    raw = (s or "").strip()
    if not raw:
        return []
    parts = re.split(r"[、,]", raw)
    out = []
    for p in parts:
        x = p.strip()
        if x:
            out.append(x)
    return out


def parse_prompt_file(prompt_path: Path) -> Dict[str, str]:
    text = prompt_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    current_types: List[str] = []
    current_block: List[str] = []
    out: Dict[str, str] = {}

    def _flush() -> None:
        nonlocal current_types, current_block
        if not current_types:
            current_block = []
            return
        content = "\n".join(current_block).strip()
        if content:
            for t in current_types:
                out[t] = content
        current_types = []
        current_block = []

    for line in lines:
        m = _TYPE_RE.match(line)
        if m:
            _flush()
            current_types = _split_types(m.group("types"))
            current_block = []
            continue
        current_block.append(line)

    _flush()
    return out


def _normalize_task_type(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip())


def _render_prompt(template: str, question: str, reference_answer: str, model_answer: str) -> str:
    p = template
    p = p.replace("{{question}}", question or "")
    p = p.replace("{{reference_answer}}", reference_answer or "")
    p = p.replace("{{model_answer}}", model_answer or "")
    return p


_thread_local = threading.local()


def _get_thread_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


def _chat_completions_url(api_base: str) -> str:
    base = (api_base or "").strip()
    if not base:
        raise ValueError("api_base is empty")
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _call_judge(
    session: requests.Session,
    api_key: str,
    api_base: str,
    model: str,
    prompt: str,
    request_timeout_s: float,
) -> str:
    url = _chat_completions_url(api_base)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict evaluator. Output ONLY valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=float(request_timeout_s))
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"no_choices: {data}")
            msg = choices[0].get("message") or {}
            content = msg.get("content") or ""
            return str(content)
        except Exception as e:
            last_error = e
            if attempt >= 5:
                break
            _sleep_backoff(attempt, cap_s=12.0)
    raise RuntimeError(f"judge_request_failed: {last_error}")


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")
_SCORE_RE = re.compile(r"\"?score\"?\s*:\s*(\d+)")


def _extract_json_object(text: str) -> Optional[dict]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        x = json.loads(raw)
        if isinstance(x, dict):
            return x
    except Exception:
        pass
    m = _JSON_OBJ_RE.search(raw)
    if not m:
        return None
    try:
        x = json.loads(m.group(0))
        return x if isinstance(x, dict) else None
    except Exception:
        return None


def _parse_score_and_reasoning(text: str) -> Tuple[Optional[int], str]:
    obj = _extract_json_object(text)
    if obj is not None:
        score = obj.get("score")
        reasoning = obj.get("reasoning")
        try:
            s_int = int(score) if score is not None else None
        except Exception:
            s_int = None
        r = str(reasoning) if reasoning is not None else (text or "").strip()
        return s_int, r

    raw = (text or "").strip()
    m = _SCORE_RE.search(raw)
    if m:
        try:
            return int(m.group(1)), raw
        except Exception:
            pass
    return None, raw


@dataclass
class JudgeResult:
    idx: int
    score: Optional[int]
    reasoning: str
    status: str
    error: Optional[str] = None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", required=True)
    p.add_argument("--output_file", required=True)
    p.add_argument(
        "--prompt_path",
        default=str((Path(__file__).resolve().parents[2] / "external" / "KnowMeBench" / "evaluate" / "evaluate prompt.md").resolve()),
    )
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--request_timeout_s", type=float, default=120.0)
    p.add_argument("--api_key", default=os.environ.get("OPENAI_API_KEY"))
    p.add_argument("--api_base", default=os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1"))
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3"))
    args = p.parse_args()

    in_dir = Path(args.input_dir)
    merged_path = in_dir / "merged_for_official_eval.json"
    if not merged_path.exists():
        raise SystemExit(f"merged_for_official_eval.json not found in: {in_dir}")

    items: List[Dict[str, Any]] = list(_load_json(merged_path))
    prompt_map = parse_prompt_file(Path(args.prompt_path))

    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    meta: Dict[str, Any] = {
        "started_at": started_at,
        "prompt_path": str(Path(args.prompt_path).resolve()),
        "judge_model": args.model,
        "total_items": len(items),
        "evaluated_items": 0,
        "average_score": 0.0,
        "status_counts": {},
    }

    if not args.api_key:
        meta["note"] = "OPENAI_API_KEY not set; all items will be skipped with status=api_config_missing"

    def _run_one(idx: int, it: Dict[str, Any]) -> JudgeResult:
        task_type = _normalize_task_type(str(it.get("task_type") or ""))
        question = str(it.get("question") or "")
        ref = str(it.get("reference_answer") or "")
        pred = str(it.get("model_answer") or "")

        if not pred.strip():
            return JudgeResult(idx=idx, score=0, reasoning="Empty/irrelevant answer", status="ok")

        tmpl = prompt_map.get(task_type)
        if not tmpl:
            return JudgeResult(
                idx=idx,
                score=0,
                reasoning=f"Task type not found in prompt file: {task_type}",
                status="skipped_unknown_task",
            )

        if not args.api_key:
            return JudgeResult(
                idx=idx,
                score=0,
                reasoning="Missing OPENAI_API_KEY",
                status="api_config_missing",
            )

        prompt = _render_prompt(tmpl, question=question, reference_answer=ref, model_answer=pred)
        try:
            session = _get_thread_session()
            out_text = _call_judge(
                session=session,
                api_key=str(args.api_key),
                api_base=str(args.api_base),
                model=str(args.model),
                prompt=prompt,
                request_timeout_s=float(args.request_timeout_s),
            )
            score, reasoning = _parse_score_and_reasoning(out_text)
            if score is None:
                return JudgeResult(
                    idx=idx,
                    score=0,
                    reasoning=f"Parse error. Raw: {out_text[:4000]}",
                    status="parse_error",
                )
            return JudgeResult(idx=idx, score=int(score), reasoning=reasoning, status="ok")
        except Exception as e:
            return JudgeResult(
                idx=idx,
                score=0,
                reasoning=f"API error: {e}",
                status="api_error",
                error=f"{e.__class__.__name__}: {e}",
            )

    results: List[Optional[JudgeResult]] = [None] * len(items)
    done = 0
    total = len(items)
    with ThreadPoolExecutor(max_workers=max(1, int(args.concurrency))) as ex:
        fut_to_idx = {ex.submit(_run_one, idx, it): idx for idx, it in enumerate(items)}
        pending = set(fut_to_idx.keys())
        last_heartbeat = time.time()
        while pending:
            done_set, pending = wait(pending, timeout=15.0, return_when=FIRST_COMPLETED)
            if not done_set:
                now = time.time()
                if now - last_heartbeat >= 15.0:
                    print(f"[{done}/{total}] judging...", flush=True)
                    last_heartbeat = now
                continue
            for fut in done_set:
                idx = fut_to_idx[fut]
                results[idx] = fut.result()
                done += 1
                if done <= 5 or done % 10 == 0 or done == total:
                    print(f"[{done}/{total}] ok", flush=True)

    details: List[Dict[str, Any]] = []
    scores: List[int] = []
    status_counts: Dict[str, int] = {}
    evaluated = 0

    for idx, it in enumerate(items):
        r = results[idx] or JudgeResult(idx=idx, score=0, reasoning="missing_result", status="internal_error")
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        if r.status == "ok":
            evaluated += 1
            if r.score is not None:
                scores.append(int(r.score))
        details.append(
            {
                "id": it.get("id"),
                "task_type": it.get("task_type"),
                "score": r.score,
                "reasoning": r.reasoning,
                "status": "success" if r.status == "ok" else r.status,
            }
        )

    meta["evaluated_items"] = evaluated
    meta["status_counts"] = dict(sorted(status_counts.items(), key=lambda kv: kv[0]))
    meta["average_score"] = (sum(scores) / len(scores)) if scores else 0.0

    out = {"meta": meta, "details": details}
    out_path = Path(args.output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

