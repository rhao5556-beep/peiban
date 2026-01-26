import argparse
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


_DIA_ID_RE = re.compile(r"^D(\d+):(\d+)$", flags=re.IGNORECASE)
_SESSION_DT_RE = re.compile(
    r"\bon\s+(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})\b",
    flags=re.IGNORECASE,
)


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


def _parse_evidence_turn_id(evidence: Any) -> Optional[int]:
    if isinstance(evidence, int):
        return evidence
    if isinstance(evidence, str):
        m = _DIA_ID_RE.match(evidence.strip())
        return int(m.group(2)) if m else None
    if isinstance(evidence, list) and evidence:
        return _parse_evidence_turn_id(evidence[0])
    return None


def _iter_sessions(conversation: Dict[str, Any]) -> Iterable[Tuple[int, str, List[Dict[str, Any]]]]:
    for k, v in conversation.items():
        m = re.match(r"^session_(\d+)$", k)
        if not m:
            continue
        idx = int(m.group(1))
        if not isinstance(v, list):
            continue
        dt = conversation.get(f"session_{idx}_date_time", "")
        yield idx, str(dt) if dt is not None else "", v


def _parse_session_base_date(session_date_time: str) -> Optional[date]:
    m = _SESSION_DT_RE.search((session_date_time or "").strip())
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).strip().lower()
    year = int(m.group(3))
    month = MONTHS.get(month_name)
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _append_relative_hints(text: str, base: Optional[date]) -> str:
    if not base:
        return text
    t = text
    low = text.lower()
    if "yesterday" in low:
        t = f"{t} | yesterday={base - timedelta(days=1):%Y-%m-%d}"
    if "today" in low:
        t = f"{t} | today={base:%Y-%m-%d}"
    if "tomorrow" in low:
        t = f"{t} | tomorrow={base + timedelta(days=1):%Y-%m-%d}"
    return t


def _normalize_turn_text(turn: Dict[str, Any], base_date: Optional[date]) -> str:
    speaker = str(turn.get("speaker") or "").strip()
    text = str(turn.get("text") or "").strip()
    dia_id = str(turn.get("dia_id") or "").strip()

    extras: List[str] = []
    blip = turn.get("blip_caption")
    if isinstance(blip, str) and blip.strip():
        extras.append(f"blip_caption={blip.strip()}")
    query = turn.get("query")
    if isinstance(query, str) and query.strip():
        extras.append(f"query={query.strip()}")
    img_url = turn.get("img_url")
    if isinstance(img_url, list) and img_url:
        extras.append(f"img_url_count={len(img_url)}")

    extra_part = f" | {'; '.join(extras)}" if extras else ""
    prefix = f"{dia_id} " if dia_id else ""
    who = f"{speaker}: " if speaker else ""
    content = f"{prefix}{who}{text}{extra_part}".strip()
    return _append_relative_hints(content, base_date).strip()


def build_transcript(conversation: Dict[str, Any]) -> List[str]:
    sessions = sorted(_iter_sessions(conversation), key=lambda x: x[0])
    lines: List[str] = []
    for idx, dt, turns in sessions:
        base_date = _parse_session_base_date(dt)
        base_iso = f"{base_date:%Y-%m-%d}" if base_date else ""
        if dt:
            if base_iso:
                lines.append(f"SESSION_{idx} @ {dt} | base_date={base_iso}".strip())
            else:
                lines.append(f"SESSION_{idx} @ {dt}".strip())
        else:
            lines.append(f"SESSION_{idx}".strip())
        for t in turns:
            if not isinstance(t, dict):
                continue
            s = _normalize_turn_text(t, base_date=base_date)
            if s:
                lines.append(s)
    return lines


@dataclass(frozen=True)
class LocomoQA:
    qid: int
    task_type: str
    question: str
    reference_answer: str
    category: Optional[int]
    evidence: List[str]
    evidence_turn_id: Optional[int]


def flatten_locomo_qa(
    locomo10: List[Dict[str, Any]],
    limit_conversations: int = 0,
    limit_questions: int = 0,
) -> List[Tuple[str, List[str], List[LocomoQA]]]:
    out: List[Tuple[str, List[str], List[LocomoQA]]] = []
    running_id = 100000
    for i, sample in enumerate(locomo10):
        if not isinstance(sample, dict):
            continue
        if limit_conversations and len(out) >= limit_conversations:
            break
        sample_id = str(sample.get("sample_id") or f"sample_{i}")
        conv = sample.get("conversation") or {}
        if not isinstance(conv, dict):
            continue
        transcript = build_transcript(conv)
        qa_list = sample.get("qa") or []
        if not isinstance(qa_list, list):
            continue
        qas: List[LocomoQA] = []
        for qa in qa_list:
            if not isinstance(qa, dict):
                continue
            if limit_questions and len(qas) >= limit_questions:
                break
            running_id += 1
            cat = qa.get("category")
            task_type = f"LoCoMo/{int(cat)}" if isinstance(cat, int) else "LoCoMo/unknown"
            question = str(qa.get("question") or "")
            ans = qa.get("answer")
            reference_answer = str(ans) if ans is not None else ""
            ev_raw = qa.get("evidence") or []
            evidence = [str(x) for x in ev_raw] if isinstance(ev_raw, list) else []
            evidence_turn_id = _parse_evidence_turn_id(ev_raw)
            qas.append(
                LocomoQA(
                    qid=running_id,
                    task_type=task_type,
                    question=question,
                    reference_answer=reference_answer,
                    category=int(cat) if isinstance(cat, int) else None,
                    evidence=evidence,
                    evidence_turn_id=evidence_turn_id,
                )
            )
        out.append((sample_id, transcript, qas))
    return out


def _get_token(session: requests.Session, backend_base_url: str, user_id: str) -> Dict[str, str]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/auth/token"
    resp = session.post(url, json={"user_id": user_id}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _memorize_batch(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    contents: List[str],
    session_id: Optional[str],
) -> List[str]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/evals/memorize_batch"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {"contents": contents}
    if session_id:
        payload["session_id"] = session_id
    resp = session.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    mem_ids = data.get("memory_ids") or []
    return [str(x) for x in mem_ids]


def _ask(
    session: requests.Session,
    backend_base_url: str,
    access_token: str,
    message: str,
    mode: str,
    eval_mode: bool,
    session_id: Optional[str],
) -> Dict[str, Any]:
    url = f"{backend_base_url.rstrip('/')}/api/v1/conversation/message"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: Dict[str, Any] = {"message": message, "mode": mode, "eval_mode": bool(eval_mode)}
    if session_id:
        payload["session_id"] = session_id
    resp = session.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()


def run_locomo10(
    backend_base_url: str,
    dataset_path: Path,
    output_dir: Path,
    mode: str = "hybrid",
    eval_mode: bool = True,
    user_id_prefix: str = "locomo",
    limit_conversations: int = 0,
    limit_questions: int = 0,
    chunk_size: int = 64,
    sleep_after_memorize_s: float = 0.5,
) -> Path:
    locomo10 = _load_json(dataset_path)
    if not isinstance(locomo10, list):
        raise RuntimeError("locomo10 dataset must be a list")

    items = flatten_locomo_qa(locomo10, limit_conversations=limit_conversations, limit_questions=limit_questions)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_dir / f"locomo10_{mode}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    sess = requests.Session()
    outputs: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        "backend_base_url": backend_base_url,
        "dataset_path": str(dataset_path),
        "mode": mode,
        "eval_mode": bool(eval_mode),
        "timestamp": ts,
        "conversations": [],
    }

    for sample_id, transcript, qas in items:
        user_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id_prefix}:{sample_id}"))
        token = _get_token(sess, backend_base_url, user_uuid)
        access_token = token["access_token"]
        user_id = token["user_id"]
        session_id = str(uuid.uuid4())

        inserted = 0
        for off in range(0, len(transcript), max(1, int(chunk_size))):
            chunk = transcript[off : off + max(1, int(chunk_size))]
            _memorize_batch(sess, backend_base_url, access_token, chunk, session_id=session_id)
            inserted += len(chunk)
        if sleep_after_memorize_s > 0:
            time.sleep(float(sleep_after_memorize_s))

        conv_outputs: List[int] = []
        for qa in qas:
            try:
                resp = _ask(
                    sess,
                    backend_base_url=backend_base_url,
                    access_token=access_token,
                    message=qa.question,
                    mode=mode,
                    eval_mode=eval_mode,
                    session_id=session_id,
                )
                reply = resp.get("reply", "")
                sid = resp.get("session_id")
                tid = resp.get("turn_id")
                cs = resp.get("context_source")
                mem_used = resp.get("memories_used") or []
                err = None
            except Exception as e:
                reply = ""
                sid = session_id
                tid = None
                cs = None
                mem_used = []
                err = f"{e.__class__.__name__}: {e}"

            outputs.append(
                {
                    "id": qa.qid,
                    "task_type": qa.task_type,
                    "sample_id": sample_id,
                    "question": qa.question,
                    "reference_answer": qa.reference_answer,
                    "model_answer": reply,
                    "meta": {
                        "affinity_base_url": backend_base_url,
                        "mode": mode,
                        "eval_mode": bool(eval_mode),
                        "user_id": user_id,
                        "session_id": sid,
                        "turn_id": tid,
                        "category": qa.category,
                        "evidence": qa.evidence,
                        "evidence_turn_id": qa.evidence_turn_id,
                        "context_source": cs,
                        "error": err,
                        "memory_ids": [str(x) for x in mem_used],
                    },
                }
            )
            conv_outputs.append(qa.qid)

        summary["conversations"].append(
            {
                "sample_id": sample_id,
                "user_id": user_id,
                "session_id": session_id,
                "transcript_turns": len(transcript),
                "memorized": inserted,
                "questions": len(qas),
                "output_qids": conv_outputs,
            }
        )

    out_file = out_dir / f"locomo.locomo10.{ts}.model_outputs.json"
    out_file.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"locomo.locomo10.{ts}.run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"))
    p.add_argument("--dataset_path", default=str(Path("data/locomo/locomo10.json").resolve()))
    p.add_argument("--output_dir", default=str(Path("outputs/locomo_run").resolve()))
    p.add_argument("--mode", choices=["graph_only", "hybrid"], default="hybrid")
    p.add_argument("--eval_mode", action="store_true", default=True)
    p.add_argument("--user_id_prefix", default="locomo")
    p.add_argument("--limit_conversations", type=int, default=0)
    p.add_argument("--limit_questions", type=int, default=0)
    p.add_argument("--chunk_size", type=int, default=64)
    p.add_argument("--sleep_after_memorize_s", type=float, default=0.5)
    args = p.parse_args()

    out_dir = run_locomo10(
        backend_base_url=args.backend_base_url,
        dataset_path=Path(args.dataset_path),
        output_dir=Path(args.output_dir),
        mode=args.mode,
        eval_mode=bool(args.eval_mode),
        user_id_prefix=str(args.user_id_prefix),
        limit_conversations=int(args.limit_conversations),
        limit_questions=int(args.limit_questions),
        chunk_size=int(args.chunk_size),
        sleep_after_memorize_s=float(args.sleep_after_memorize_s),
    )
    print(str(out_dir))


if __name__ == "__main__":
    main()
