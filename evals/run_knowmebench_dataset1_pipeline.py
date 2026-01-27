import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


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


def _parse_date_from_question(question: str) -> Optional[str]:
    q = question or ""
    m = re.search(
        r"\b(?:from|on|in|during|after|before)\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\b",
        q,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    month_name = m.group(1).strip().lower()
    day = int(m.group(2))
    year = int(m.group(3))
    month = MONTHS.get(month_name)
    if not month:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_answers(answer_path: Path) -> Dict[int, Any]:
    answers = _load_json(answer_path)
    out: Dict[int, Any] = {}
    for a in answers:
        if "id" in a:
            out[int(a["id"])] = a
    return out


def _row_to_line(r: Dict[str, Any]) -> str:
    rid = r.get("id")
    ts = r.get("timestamp")
    loc = r.get("location")
    action = r.get("action")
    dialogue = r.get("dialogue")
    env = r.get("environment")
    bg = r.get("background")
    inner = r.get("inner_thought")
    parts = []
    if action:
        parts.append(f"action: {action}")
    if dialogue:
        parts.append(f"dialogue: {dialogue}")
    if env:
        parts.append(f"environment: {env}")
    if bg:
        parts.append(f"background: {bg}")
    if inner:
        parts.append(f"inner_thought: {inner}")
    parts_joined = " | ".join(parts) if parts else ""
    return f"[id {rid}] {ts} @ {loc}: {parts_joined}".strip()


def _build_record_context(dataset_rows: List[Dict[str, Any]], iso_date: str) -> Tuple[str, List[int]]:
    selected = [
        r
        for r in dataset_rows
        if isinstance(r.get("timestamp"), str) and r["timestamp"].startswith(iso_date)
    ]
    selected_ids = [int(r["id"]) for r in selected if "id" in r]
    return "\n".join(_row_to_line(r) for r in selected), selected_ids


def _build_record_context_by_id_window(
    dataset_rows: List[Dict[str, Any]],
    evidence_ids: List[int],
    context_window: int,
) -> Tuple[str, List[int]]:
    if not evidence_ids:
        return "", []
    min_id = min(evidence_ids)
    max_id = max(evidence_ids)
    lo = max(0, min_id - context_window)
    hi = max_id + context_window

    selected = [
        r
        for r in dataset_rows
        if isinstance(r.get("id"), int) and lo <= r["id"] <= hi
    ]
    selected_ids = [int(r["id"]) for r in selected if "id" in r]
    return "\n".join(_row_to_line(r) for r in selected), selected_ids


def _sleep_backoff(attempt: int, cap_s: float) -> None:
    base = 1.5 ** attempt
    jitter = random.random() * 0.5
    time.sleep(min(cap_s, base + jitter))


def _get_token(backend_base_url: str, user_id: Optional[str]) -> Dict[str, str]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/auth/token"
    payload = {"user_id": user_id} if user_id else {}
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt >= 5:
                break
            _sleep_backoff(attempt, cap_s=10.0)
    raise RuntimeError(f"failed_to_get_token: {last_error}")


_thread_local = threading.local()


def _get_thread_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


def _ask_backend(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    message: str,
    mode: str,
    eval_mode: bool,
    eval_task_type: Optional[str],
    evidence_ids: Optional[List[int]],
    session_id: Optional[str],
    request_timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {
        "message": message,
        "mode": mode,
        "eval_mode": bool(eval_mode),
        "eval_task_type": eval_task_type,
    }
    if evidence_ids:
        payload["eval_evidence_ids"] = evidence_ids
    if session_id:
        payload["session_id"] = session_id

    last_error: Exception | None = None
    for attempt in range(8):
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=float(request_timeout_s))
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} {resp.text}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt >= 7:
                break
            _sleep_backoff(attempt, cap_s=20.0)
    raise RuntimeError(f"backend_request_failed: {last_error}")


def _task_slug(task_type: str) -> str:
    return task_type.strip().lower().replace(" ", "_").replace("-", "_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend_base_url",
        default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--dataset_dir",
        default=str(Path("external/KnowMeBench/KnowmeBench/dataset1").resolve()),
    )
    parser.add_argument(
        "--output_dir",
        default=str(Path("outputs/knowmebench_run").resolve()),
    )
    parser.add_argument("--mode", choices=["graph_only", "hybrid"], default="graph_only")
    parser.add_argument("--eval_mode", action="store_true", default=True)
    parser.add_argument("--user_id", default=None)
    parser.add_argument("--limit_per_task", type=int, default=0)
    parser.add_argument("--context_window", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--request_timeout_s", type=float, default=90.0)
    parser.add_argument("--task", action="append", default=[])
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    dataset_rows = _load_json(dataset_dir / "input" / "dataset1.json")

    question_paths = sorted((dataset_dir / "question").glob("*_questions.json"))
    answer_paths = {
        p.name.replace("_questions.json", "_answers.json"): p
        for p in (dataset_dir / "answer").glob("*_answers.json")
    }

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) / f"ds1_pipeline_{args.mode}_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    token_data = _get_token(args.backend_base_url, args.user_id)
    access_token = token_data["access_token"]
    user_id = token_data["user_id"]

    run_summary = {
        "backend_base_url": args.backend_base_url,
        "mode": args.mode,
        "eval_mode": bool(args.eval_mode),
        "user_id": user_id,
        "timestamp": run_ts,
        "context_window": args.context_window,
        "concurrency": args.concurrency,
        "tasks": [],
    }

    selected_task_set = {t.strip() for t in (args.task or []) if t and t.strip()}

    for q_path in question_paths:
        task_type = q_path.name.replace("_questions.json", "")
        if selected_task_set and task_type not in selected_task_set:
            continue

        slug = _task_slug(task_type)
        a_path = answer_paths.get(f"{task_type}_answers.json")
        answers = _load_answers(a_path) if a_path else {}
        questions = _load_json(q_path)

        session_id: Optional[str] = None

        q_iter = questions
        if args.limit_per_task and args.limit_per_task > 0:
            q_iter = questions[: args.limit_per_task]

        def _normalize_evidence_ids(ev: Any) -> List[int]:
            if ev is None:
                return []
            if isinstance(ev, int):
                return [ev]
            if isinstance(ev, list):
                out: List[int] = []
                for x in ev:
                    if isinstance(x, int):
                        out.append(x)
                return out
            return []

        def _run_one(idx: int, item: Dict[str, Any]) -> Dict[str, Any]:
            qid = int(item["id"])
            question = str(item["question"])

            ans_obj = answers.get(qid)
            reference_answer = ""
            evidence = None
            evidence_ids: List[int] = []
            if ans_obj is not None:
                reference_answer = ans_obj.get("answer", "")
                evidence = ans_obj.get("evidence")
                evidence_ids = _normalize_evidence_ids(evidence)

            context_text = ""
            context_ids: List[int] = []
            iso_date = _parse_date_from_question(question)
            if evidence_ids:
                context_text, context_ids = _build_record_context_by_id_window(
                    dataset_rows=dataset_rows,
                    evidence_ids=evidence_ids,
                    context_window=args.context_window,
                )
            elif iso_date:
                context_text, context_ids = _build_record_context(dataset_rows, iso_date)

            injected_message = question
            if context_text:
                injected_message = (
                    "Below is the record excerpt. Use it as the only factual source.\n"
                    f"{context_text}\n\n"
                    f"Question: {question}\n"
                    "Answer:"
                )

            try:
                session = _get_thread_session()
                resp = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    message=injected_message,
                    mode=args.mode,
                    eval_mode=args.eval_mode,
                    eval_task_type=task_type,
                    evidence_ids=evidence_ids,
                    session_id=session_id,
                    request_timeout_s=args.request_timeout_s,
                )
                reply = resp.get("reply", "")
                cs = resp.get("context_source")
                turn_id = resp.get("turn_id")
                sid = resp.get("session_id")
            except Exception as e:
                reply = ""
                cs = None
                turn_id = None
                sid = None
                err = f"{e.__class__.__name__}: {e}"
            else:
                err = None

            return {
                "id": qid,
                "task_type": task_type,
                "question": question,
                "reference_answer": reference_answer,
                "model_answer": reply,
                "meta": {
                    "affinity_base_url": args.backend_base_url,
                    "mode": args.mode,
                    "eval_mode": bool(args.eval_mode),
                    "user_id": user_id,
                    "session_id": sid,
                    "turn_id": turn_id,
                    "evidence": evidence,
                    "record_date": iso_date,
                    "record_ids": context_ids,
                    "context_source": cs,
                    "error": err,
                },
            }

        outputs: List[Dict[str, Any]] = [None] * len(q_iter)  # type: ignore[list-item]
        total_n = len(q_iter)
        print(
            f"==> running task: {task_type} n={total_n} concurrency={args.concurrency}",
            file=sys.stderr,
            flush=True,
        )
        done = 0
        with ThreadPoolExecutor(max_workers=max(1, int(args.concurrency))) as ex:
            fut_to_idx = {ex.submit(_run_one, idx, item): idx for idx, item in enumerate(q_iter)}
            pending = set(fut_to_idx.keys())
            last_heartbeat = time.time()
            while pending:
                done_set, pending = wait(pending, timeout=15.0, return_when=FIRST_COMPLETED)
                if not done_set:
                    now = time.time()
                    if now - last_heartbeat >= 15.0:
                        print(f"[{done}/{total_n}] running...", file=sys.stderr, flush=True)
                        last_heartbeat = now
                    continue

                for fut in done_set:
                    idx = fut_to_idx[fut]
                    outputs[idx] = fut.result()
                    done += 1
                    if done <= 5 or done % 10 == 0 or done == total_n:
                        qid = outputs[idx].get("id") if outputs[idx] else None
                        status = (
                            "ok"
                            if outputs[idx] and not outputs[idx]["meta"].get("error")
                            else "err"
                        )
                        print(f"[{done}/{total_n}] {status} id={qid}", file=sys.stderr, flush=True)

        out_file = out_dir / f"knowmebench.dataset1.{slug}.{run_ts}.model_outputs.json"
        out_file.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
        run_summary["tasks"].append(
            {"task_type": task_type, "questions": len(outputs), "output_file": str(out_file)}
        )

    (out_dir / f"knowmebench.dataset1.{run_ts}.run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    merged: List[Dict[str, Any]] = []
    for t in run_summary["tasks"]:
        merged.extend(_load_json(Path(t["output_file"])))
    merged_file = out_dir / "merged_for_official_eval.json"
    merged_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(out_dir))


if __name__ == "__main__":
    main()

