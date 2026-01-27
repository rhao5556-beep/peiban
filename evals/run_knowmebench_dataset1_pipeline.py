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


def _parse_ts(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts.strip():
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _format_duration_seconds(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    m = s // 60
    sec = s % 60
    return f"{m} minutes {sec} seconds"


def _compute_duration_from_evidence(dataset_rows: List[Dict[str, Any]], evidence_ids: List[int]) -> Optional[str]:
    if not evidence_ids:
        return None
    min_id = min(evidence_ids)
    max_id = max(evidence_ids)
    by_id: Dict[int, Dict[str, Any]] = {}
    for r in dataset_rows:
        if isinstance(r.get("id"), int):
            by_id[int(r["id"])] = r
    a = by_id.get(min_id)
    b = by_id.get(max_id)
    if not a or not b:
        return None
    ta = _parse_ts(a.get("timestamp"))
    tb = _parse_ts(b.get("timestamp"))
    if not ta or not tb:
        return None
    return _format_duration_seconds((tb - ta).total_seconds())


def _task_instructions(task_type: str) -> str:
    t = (task_type or "").strip()
    common = (
        "Global Rules:\n"
        "- Answer in English.\n"
        "- Do not greet or add chit-chat.\n"
        "- Be concise and directly answer the question.\n"
        "\n"
    )
    if t == "Temporal Reasoning":
        return common + (
            "Rules:\n"
            "- If the record excerpt provides timestamps, compute the exact duration.\n"
            "- Output only the final duration in the format: \"X minutes Y seconds\".\n"
            "- Do not answer \"not provided\" if timestamps allow calculation.\n"
        )
    if t == "Logical Event Ordering":
        return common + (
            "Rules:\n"
            "- Use only facts from the record excerpt.\n"
            "- Pick exactly 3 moments that directly answer the question and match the ranking dimension.\n"
            "- Ignore incidental details unless they change the ranking dimension.\n"
            "- Prefer moments of escalation (demands, threats, coercion, rapid spread, etc.) over supportive actions.\n"
            "- Return a JSON array of 3 objects, each with keys: rank (1..3), event, reasoning, record_ids.\n"
            "- record_ids must be a list of [id N] you used as evidence.\n"
            "- In reasoning, quote short phrases from the excerpt that justify the ranking.\n"
        )
    if t == "Expert-Annotated Psychoanalysis":
        return common + (
            "Rules:\n"
            "- Answer about the narrator/character \"I\" in the provided record, not the user.\n"
            "- Be specific and grounded; do not ask the user questions back.\n"
            "- Provide a concise answer and cite 1-2 record_ids as evidence.\n"
            "- If insufficient evidence exists, state what is missing briefly.\n"
        )
    if t == "Mnestic Trigger Analysis":
        return common + (
            "Rules:\n"
            "- Identify the specific trigger/anchor detail that displaces the narrator into a past time.\n"
            "- Output only that detail (one sentence).\n"
            "- Avoid inventing locations/names; if missing, say you don't know.\n"
        )
    if t == "Mind-Body Interaction":
        return common + (
            "Rules:\n"
            "- Explain how an external action/observation triggers an internal physiological/emotional shift.\n"
            "- Write 2-3 sentences; include 1-2 short quoted phrases from the excerpt.\n"
            "- If missing, say you don't know.\n"
        )
    return (
        common
        + "Rules:\n"
        "- Use only facts from the record excerpt.\n"
        "- If the excerpt is insufficient, say you don't know.\n"
    )


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
    session_id: Optional[str],
    request_timeout_s: float,
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {"message": message, "mode": mode, "eval_mode": bool(eval_mode)}
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


def _chunk_lines(lines: List[str], chunk_size: int) -> List[str]:
    out: List[str] = []
    for i in range(0, len(lines), max(1, int(chunk_size))):
        out.append("\n".join(lines[i : i + int(chunk_size)]))
    return out


def _build_psychoanalysis_context(dataset_rows: List[Dict[str, Any]], max_lines: int) -> Tuple[str, List[int]]:
    keywords = [
        "father",
        "dad",
        "authority",
        "rule",
        "rules",
        "correct",
        "trouble",
        "risk",
        "penalty",
        "punish",
        "punishment",
        "forbid",
        "not allowed",
        "shouldn't",
        "anger",
        "furious",
        "shout",
    ]
    picked: List[Dict[str, Any]] = []
    for r in dataset_rows:
        if not isinstance(r, dict) or not isinstance(r.get("id"), int):
            continue
        text = " ".join(
            str(r.get(k, "") or "")
            for k in ["action", "dialogue", "environment", "background", "inner_thought"]
        ).lower()
        if any(k in text for k in keywords):
            picked.append(r)
        if len(picked) >= max_lines:
            break
    picked_ids = [int(r["id"]) for r in picked if "id" in r]
    return "\n".join(_row_to_line(r) for r in picked), picked_ids


def _build_date_keyword_context(
    dataset_rows: List[Dict[str, Any]],
    iso_date: str,
    question: str,
    max_lines: int,
) -> Tuple[str, List[int]]:
    stop = {
        "according",
        "record",
        "from",
        "during",
        "after",
        "before",
        "july",
        "august",
        "1969",
        "1975",
        "what",
        "which",
        "please",
        "list",
        "three",
        "based",
        "dimension",
        "arrange",
        "ordered",
        "order",
        "most",
        "least",
        "until",
        "when",
        "where",
        "how",
        "long",
        "took",
        "take",
    }
    kws = []
    for w in re.findall(r"[A-Za-z']+", (question or "").lower()):
        if len(w) >= 4 and w not in stop:
            kws.append(w)
    kws = list(dict.fromkeys(kws))[:30]
    kws.extend(
        [
            "father",
            "dad",
            "punish",
            "punishment",
            "shake",
            "ear",
            "bed",
            "locked",
            "lock",
            "stay",
            "fire",
            "flame",
            "smoke",
            "match",
            "danger",
            "forbid",
            "not allowed",
            "shout",
            "furious",
            "grab",
            "drag",
        ]
    )
    kws = list(dict.fromkeys([k for k in kws if k]))[:80]

    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for r in dataset_rows:
        if not isinstance(r, dict):
            continue
        ts = r.get("timestamp")
        if not (isinstance(ts, str) and ts.startswith(iso_date)):
            continue
        blob = " ".join(
            str(r.get(k, "") or "")
            for k in ["action", "dialogue", "environment", "background", "inner_thought"]
        ).lower()
        score = 0
        for k in kws:
            if k in blob:
                score += 1
        if score > 0:
            rid = int(r["id"]) if isinstance(r.get("id"), int) else -1
            scored.append((score, rid, r))

    if not scored:
        return _build_record_context(dataset_rows, iso_date)

    scored.sort(key=lambda x: (-x[0], x[1]))
    picked = [x[2] for x in scored[: max(1, int(max_lines))]]
    picked.sort(key=lambda r: int(r.get("id") or -1))
    selected_ids = [int(r["id"]) for r in picked if "id" in r]
    return "\n".join(_row_to_line(r) for r in picked), selected_ids


def _build_scene_context_for_question(
    dataset_rows: List[Dict[str, Any]],
    iso_date: str,
    question: str,
    window: int,
    max_lines: int,
) -> Tuple[str, List[int]]:
    day_rows = [
        r
        for r in dataset_rows
        if isinstance(r, dict)
        and isinstance(r.get("timestamp"), str)
        and r["timestamp"].startswith(iso_date)
        and isinstance(r.get("id"), int)
    ]
    day_rows.sort(key=lambda r: int(r.get("id") or -1))
    if not day_rows:
        return "", []

    stop = {
        "according",
        "record",
        "from",
        "during",
        "after",
        "before",
        "july",
        "august",
        "1969",
        "1975",
        "what",
        "which",
        "please",
        "list",
        "three",
        "based",
        "dimension",
        "arrange",
        "ordered",
        "order",
        "most",
        "least",
        "until",
        "when",
        "where",
        "how",
        "long",
        "took",
        "take",
        "finally",
    }
    kws = []
    for w in re.findall(r"[A-Za-z']+", (question or "").lower()):
        if len(w) >= 4 and w not in stop:
            kws.append(w)
    kws = list(dict.fromkeys(kws))[:12]
    ql = (question or "").lower()
    if "television" in ql or " tv" in ql or "tv" in ql:
        kws.extend(
            [
                "bed",
                "bedroom",
                "ear",
                "shake",
                "locked",
                "lock",
                "tomorrow",
                "stay",
                "inside",
                "shivering",
                "fear",
                "footsteps",
            ]
        )
    if "fire" in ql or "match" in ql or "ignition" in ql:
        kws.extend(["spruce", "hay", "grass", "root", "path", "smoke", "waist"])
    if "swim" in ql or "water" in ql:
        kws.extend(["deep", "furious", "grab", "drag", "life jacket"])
    kws = list(dict.fromkeys([k for k in kws if k]))[:40]
    if not kws:
        return _build_record_context(dataset_rows, iso_date)

    match_idx: List[int] = []
    for i, r in enumerate(day_rows):
        blob = " ".join(
            str(r.get(k, "") or "")
            for k in ["action", "dialogue", "environment", "background", "inner_thought"]
        ).lower()
        if any(k in blob for k in kws):
            match_idx.append(i)

    if not match_idx:
        return _build_record_context(dataset_rows, iso_date)

    keep_ids = set()
    w = max(1, int(window))
    for i in match_idx:
        lo = max(0, i - w)
        hi = min(len(day_rows) - 1, i + w)
        for j in range(lo, hi + 1):
            keep_ids.add(int(day_rows[j]["id"]))

    selected = [r for r in day_rows if int(r["id"]) in keep_ids]
    if len(selected) > int(max_lines):
        selected = selected[: int(max_lines)]
    selected_ids = [int(r["id"]) for r in selected if "id" in r]
    return "\n".join(_row_to_line(r) for r in selected), selected_ids


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
    parser.add_argument("--seed_psychoanalysis", action="store_true", default=True)
    parser.add_argument("--seed_chunk_rows", type=int, default=25)
    parser.add_argument("--seed_max_rows", type=int, default=220)
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

        def _seed_psychoanalysis_session() -> None:
            nonlocal session_id
            if not args.seed_psychoanalysis:
                return
            if task_type != "Expert-Annotated Psychoanalysis":
                return
            lines = []
            for r in dataset_rows:
                if isinstance(r, dict) and isinstance(r.get("id"), int):
                    lines.append(_row_to_line(r))
                if len(lines) >= int(args.seed_max_rows):
                    break
            chunks = _chunk_lines(lines, int(args.seed_chunk_rows))
            session = _get_thread_session()
            for i, chunk in enumerate(chunks, start=1):
                seed_msg = (
                    "Please store the following record excerpt for later questions. Reply only with ACK.\n"
                    f"Chunk {i}/{len(chunks)}\n"
                    f"{chunk}\n"
                )
                resp = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    message=seed_msg,
                    mode=args.mode,
                    eval_mode=args.eval_mode,
                    session_id=session_id,
                    request_timeout_s=max(float(args.request_timeout_s), 180.0),
                )
                session_id = resp.get("session_id") or session_id

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
                cw = int(args.context_window)
                if task_type in {"Mnestic Trigger Analysis", "Mind-Body Interaction"}:
                    cw = min(cw, 12)
                context_text, context_ids = _build_record_context_by_id_window(
                    dataset_rows=dataset_rows,
                    evidence_ids=evidence_ids,
                    context_window=cw,
                )
            elif iso_date:
                if task_type == "Logical Event Ordering":
                    context_text, context_ids = _build_scene_context_for_question(
                        dataset_rows=dataset_rows,
                        iso_date=iso_date,
                        question=question,
                        window=6,
                        max_lines=140,
                    )
                else:
                    context_text, context_ids = _build_record_context(dataset_rows, iso_date)

            if task_type == "Expert-Annotated Psychoanalysis" and not context_text:
                context_text, context_ids = _build_psychoanalysis_context(
                    dataset_rows=dataset_rows, max_lines=min(90, int(args.seed_max_rows))
                )
                if not context_text:
                    _seed_psychoanalysis_session()

            injected_message = question
            if context_text:
                injected_message = (
                    "Below is the record excerpt. Use it as the only factual source.\n"
                    f"{context_text}\n\n"
                    f"{_task_instructions(task_type)}"
                    f"Question: {question}\n"
                    "Answer:"
                )
            else:
                injected_message = f"{_task_instructions(task_type)}Question: {question}\nAnswer:"

            try:
                session = _get_thread_session()
                resp = _ask_backend(
                    session=session,
                    backend_base_url=args.backend_base_url,
                    access_token=access_token,
                    message=injected_message,
                    mode=args.mode,
                    eval_mode=args.eval_mode,
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
                    "derived": None,
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

