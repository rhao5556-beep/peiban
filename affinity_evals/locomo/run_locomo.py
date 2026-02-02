import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

import requests


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError("dataset_path must be a JSON list")
    return data


def _build_dialogue_index(
    conv: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Tuple[str, int]]]:
    conversation = conv.get("conversation") or {}
    dia_map: Dict[str, Dict[str, str]] = {}
    pos_map: Dict[str, Tuple[str, int]] = {}

    for k, v in conversation.items():
        if not (isinstance(k, str) and k.startswith("session_") and isinstance(v, list)):
            continue
        if not k.startswith("session_") or not k[len("session_") :].isdigit():
            continue
        session_key = k
        session_dt_key = f"{session_key}_date_time"
        session_dt = str(conversation.get(session_dt_key) or "").strip()
        for item in v:
            if not isinstance(item, dict):
                continue
            dia_id = str(item.get("dia_id") or "").strip()
            if not dia_id:
                continue
            idx = len(pos_map)
            dia_map[dia_id] = {
                "speaker": str(item.get("speaker") or "").strip(),
                "text": str(item.get("text") or "").strip(),
                "session_key": session_key,
                "session_date_time": session_dt,
            }
            pos_map[dia_id] = (session_key, idx)
    return dia_map, pos_map


def _build_context_from_evidence(
    conv: Dict[str, Any],
    evidence: List[str],
    window: int,
    max_lines: int,
) -> str:
    if not evidence:
        return ""
    mapping, pos_map = _build_dialogue_index(conv)
    conversation = conv.get("conversation") or {}

    picked: Set[str] = set()
    session_keys: List[str] = []
    for e in evidence:
        dia_id = str(e).strip()
        if dia_id in pos_map:
            s, _ = pos_map[dia_id]
            if s not in session_keys:
                session_keys.append(s)

    for e in evidence:
        dia_id = str(e).strip()
        if dia_id in pos_map:
            session_key, _ = pos_map[dia_id]
            session_list = conversation.get(session_key) or []
            if not isinstance(session_list, list):
                continue
            idx_in_session = None
            for i, it in enumerate(session_list):
                if isinstance(it, dict) and str(it.get("dia_id") or "").strip() == dia_id:
                    idx_in_session = i
                    break
            if idx_in_session is None:
                continue
            lo = max(0, idx_in_session - max(0, int(window)))
            hi = min(len(session_list) - 1, idx_in_session + max(0, int(window)))
            for j in range(lo, hi + 1):
                it = session_list[j]
                if not isinstance(it, dict):
                    continue
                d = str(it.get("dia_id") or "").strip()
                if d:
                    picked.add(d)

    lines: List[str] = []
    for session_key in session_keys:
        session_dt = str((conversation or {}).get(f"{session_key}_date_time") or "").strip()
        if session_dt:
            lines.append(f"Session time: {session_dt}")
        session_list = conversation.get(session_key) or []
        if not isinstance(session_list, list):
            continue
        for it in session_list:
            if not isinstance(it, dict):
                continue
            dia_id = str(it.get("dia_id") or "").strip()
            if dia_id not in picked:
                continue
            hit = mapping.get(dia_id) or {}
            speaker = str(hit.get("speaker") or "").strip()
            text = str(hit.get("text") or "").strip()
            if speaker:
                lines.append(f"- [{dia_id}] {speaker}: {text}")
            else:
                lines.append(f"- [{dia_id}] {text}")
            if len(lines) >= max_lines:
                break
        if len(lines) >= max_lines:
            break

    return "\n".join(lines)


def _get_token(backend_base_url: str, user_seed: str, timeout_s: float) -> Tuple[str, str]:
    resp = requests.post(
        f"{backend_base_url.rstrip('/')}/api/v1/auth/token",
        json={"user_id": user_seed},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    payload = resp.json() or {}
    token = payload.get("access_token")
    user_id = payload.get("user_id")
    if not token or not user_id:
        raise RuntimeError("auth/token did not return access_token/user_id")
    return str(token), str(user_id)


def _ask_backend(
    backend_base_url: str,
    token: str,
    message: str,
    session_id: Optional[str],
    mode: str,
    eval_mode: bool,
    answer_style: Optional[str],
    eval_task_type: Optional[str],
    timeout_s: float,
) -> Dict[str, Any]:
    resp = requests.post(
        f"{backend_base_url.rstrip('/')}/api/v1/conversation/message",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": message,
            "session_id": session_id,
            "mode": mode,
            "eval_mode": bool(eval_mode),
            "answer_style": answer_style,
            "eval_task_type": eval_task_type,
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    return resp.json() or {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", required=True)
    p.add_argument("--dataset_path", required=True)
    p.add_argument("--output_dir", required=True)
    p.add_argument("--mode", choices=["hybrid", "graph_only"], default="hybrid")
    p.add_argument("--eval_mode", action="store_true")
    p.add_argument("--limit_conversations", type=int, default=0)
    p.add_argument("--limit_questions", type=int, default=0)
    p.add_argument("--categories", nargs="*", type=int, default=[])
    p.add_argument("--limit_per_category", type=int, default=0)
    p.add_argument("--evidence_window", type=int, default=2)
    p.add_argument("--chunk_size", type=int, default=64)
    p.add_argument("--sleep_after_memorize_s", type=float, default=0.0)
    p.add_argument("--request_timeout_s", type=float, default=40.0)
    p.add_argument("--answer_style", default="")
    args = p.parse_args()

    backend_base_url = str(args.backend_base_url)
    dataset_path = Path(args.dataset_path)
    output_root = Path(args.output_dir)

    dataset = _load_dataset(dataset_path)
    dataset_name = dataset_path.stem or "locomo"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    eval_dir = output_root / f"{dataset_name}_{args.mode}_{ts}"
    eval_dir.mkdir(parents=True, exist_ok=True)

    user_seed = f"locomo-{uuid.uuid4().hex}"
    token, user_id = _get_token(backend_base_url, user_seed=user_seed, timeout_s=10.0)

    conv_limit = int(args.limit_conversations or 0)
    convs = dataset[:conv_limit] if conv_limit > 0 else dataset

    outputs: List[Dict[str, Any]] = []
    q_global_id = 0

    limit_per_category = int(args.limit_per_category or 0)
    categories = [int(x) for x in (args.categories or []) if isinstance(x, int) and x > 0]
    if limit_per_category > 0 and not categories:
        categories = [1, 2, 3, 4]

    selected: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    if limit_per_category > 0 and categories:
        picked_count: Dict[int, int] = {c: 0 for c in categories}
        for conv_i, conv in enumerate(convs, start=1):
            qa = conv.get("qa") or []
            if not isinstance(qa, list):
                continue
            for qa_item in qa:
                cat = (qa_item or {}).get("category")
                cat_i = int(cat) if isinstance(cat, int) else None
                if cat_i is None or cat_i not in picked_count:
                    continue
                if picked_count[cat_i] >= limit_per_category:
                    continue
                selected.append((conv_i, conv, qa_item))
                picked_count[cat_i] += 1
                if all(picked_count[c] >= limit_per_category for c in categories):
                    break
            if all(picked_count[c] >= limit_per_category for c in categories):
                break
    else:
        for conv_i, conv in enumerate(convs, start=1):
            qa = conv.get("qa") or []
            if not isinstance(qa, list):
                continue
            q_limit = int(args.limit_questions or 0)
            qas = qa[:q_limit] if q_limit > 0 else qa
            for qa_item in qas:
                selected.append((conv_i, conv, qa_item))

    session_id: Optional[str] = None
    total_n = len(selected)
    for idx, (conv_i, conv, qa_item) in enumerate(selected, start=1):
        q_global_id += 1
        question = str((qa_item or {}).get("question") or "").strip()
        reference = (qa_item or {}).get("answer")
        evidence = (qa_item or {}).get("evidence") or []
        if not isinstance(evidence, list):
            evidence = []
        category = (qa_item or {}).get("category")
        category_int = int(category) if isinstance(category, int) else None

        ctx = _build_context_from_evidence(
            conv,
            evidence=evidence,
            window=int(args.evidence_window or 0),
            max_lines=40,
        )
        if ctx:
            prompt = (
                "Below is the conversation excerpt. Use it as the only factual source.\n"
                f"{ctx}\n\n"
                f"Question: {question}\n"
                "Answer:"
            )
        else:
            prompt = question

        print(f"[{idx}/{total_n}] id={q_global_id} category={category_int}", flush=True)

        started = time.perf_counter()
        try:
            resp = _ask_backend(
                backend_base_url=backend_base_url,
                token=token,
                message=prompt,
                session_id=session_id,
                mode=str(args.mode),
                eval_mode=bool(args.eval_mode),
                answer_style=str(args.answer_style or "").strip() or None,
                eval_task_type="LoCoMo" if bool(args.eval_mode) else None,
                timeout_s=float(args.request_timeout_s),
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            session_id = str(resp.get("session_id") or session_id or "")

            outputs.append(
                {
                    "id": q_global_id,
                    "task_type": "LoCoMo",
                    "question": question,
                    "reference_answer": reference,
                    "model_answer": resp.get("reply", ""),
                    "category": category_int,
                    "meta": {
                        "backend_base_url": backend_base_url,
                        "mode": str(args.mode),
                        "eval_mode": bool(args.eval_mode),
                        "user_id": user_id,
                        "conversation_index": conv_i,
                        "session_id": session_id,
                        "turn_id": resp.get("turn_id"),
                        "evidence": evidence,
                        "category": category_int,
                        "elapsed_ms": elapsed_ms,
                        "context_source": resp.get("context_source"),
                    },
                }
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            outputs.append(
                {
                    "id": q_global_id,
                    "task_type": "LoCoMo",
                    "question": question,
                    "reference_answer": reference,
                    "model_answer": "",
                    "category": category_int,
                    "meta": {
                        "backend_base_url": backend_base_url,
                        "mode": str(args.mode),
                        "eval_mode": bool(args.eval_mode),
                        "user_id": user_id,
                        "conversation_index": conv_i,
                        "session_id": session_id,
                        "evidence": evidence,
                        "category": category_int,
                        "elapsed_ms": elapsed_ms,
                        "error": str(e),
                    },
                }
            )
            print(f"ERROR: question id={q_global_id} failed: {e}", file=sys.stderr, flush=True)

    out_name = f"{dataset_name}.{args.mode}.{ts}.model_outputs.json"
    out_path = eval_dir / out_name
    out_path.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(eval_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
