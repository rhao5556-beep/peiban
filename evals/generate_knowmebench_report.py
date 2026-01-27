import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x)


def _markdown_escape(s: str) -> str:
    return (s or "").replace("\r\n", "\n").replace("\r", "\n")


def _shorten(s: str, n: int = 800) -> str:
    x = _markdown_escape(s).strip()
    if len(x) <= n:
        return x
    return x[: n - 10] + "\n...\n(truncated)"


@dataclass(frozen=True)
class ItemKey:
    task_type: str
    item_id: int


def _index_outputs(merged: List[Dict[str, Any]]) -> Dict[ItemKey, Dict[str, Any]]:
    idx: Dict[ItemKey, Dict[str, Any]] = {}
    for it in merged:
        try:
            tid = int(it.get("id"))
        except Exception:
            continue
        task_type = _safe_str(it.get("task_type")).strip()
        if not task_type:
            continue
        idx[ItemKey(task_type=task_type, item_id=tid)] = it
    return idx


def _suggestions_for_task(task_type: str, low_score_examples: List[Dict[str, Any]]) -> List[str]:
    t = (task_type or "").strip()
    if not t:
        return []

    base: Dict[str, List[str]] = {
        "Information Extraction": [
            "强化实体对齐：回答前先抽取题干中的实体名/属性并逐项对照记录",
            "减少“合理补充”：除非有证据，否则不要追加背景细节",
        ],
        "Adversarial Abstention": [
            "加入“可回答性检查”：若记录无证据或题干诱导，优先明确拒答/说明缺失信息",
            "对含糊问题输出结构化澄清：列出需要的缺失字段并给出无法判断的原因",
        ],
        "Temporal Reasoning": [
            "将时间线显式化：先列出涉及的日期/时间点，再做推理与比较",
            "检索时扩大时间窗口：避免只取单日导致跨日线索丢失",
        ],
        "Logical Event Ordering": [
            "输出排序依据：每个事件给出同一维度的评分理由（风险/因果/紧急程度）",
            "避免混用维度：明确是按“危险性/时间先后/重要性”哪一种排序",
        ],
        "Mnestic Trigger Analysis": [
            "把触发线索与回忆内容一一对应：线索→被激活的记忆片段→理由",
            "减少泛化心理分析：优先使用记录中的具体线索词/地点/物品",
        ],
        "Mind-Body Interaction": [
            "先复述冲突点（心理 vs 生理）再解释机制，避免直接下结论",
            "回答保持可证据化：不引入未在记录出现的病史/诊断",
        ],
        "Expert-Annotated Psychoanalysis": [
            "分层解释：行为表象→动机假设→记录证据→不确定性声明",
            "降低臆测：遇到证据不足时给出多种可能并标注置信度",
        ],
    }

    extra: List[str] = []
    if low_score_examples:
        err_counts = defaultdict(int)
        for ex in low_score_examples:
            reason = _safe_str(ex.get("reasoning", "")).lower()
            if "halluc" in reason or "fabricat" in reason:
                err_counts["hallucination"] += 1
            if "missing" in reason or "omit" in reason:
                err_counts["missing"] += 1
            if "incorrect" in reason or "wrong" in reason:
                err_counts["incorrect"] += 1
            if "refus" in reason or "abstain" in reason:
                err_counts["abstention"] += 1
        if err_counts.get("hallucination"):
            extra.append("加强“证据优先”约束：没有记录证据就不写")
        if err_counts.get("missing"):
            extra.append("补齐关键信息：先覆盖参考答案的核心字段再扩展")
        if err_counts.get("incorrect"):
            extra.append("增加自检：输出前对比记录摘录中的实体/时间/地点是否一致")

    return base.get(t, []) + extra


def _render_table(rows: List[Tuple[str, int, int, float, int, int]]) -> str:
    lines = [
        "| 任务 | 总数 | 评估数 | 平均分 | 低分(<=2) | 高分(>=4) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for task, total_n, eval_n, avg, low_n, high_n in rows:
        lines.append(f"| {task} | {total_n} | {eval_n} | {avg:.2f} | {low_n} | {high_n} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_dir", required=True, help="outputs/knowmebench_run/ds1_pipeline_... directory")
    parser.add_argument("--judge_file", default="", help="path to judge_results.json (default: <run_dir>/judge_results.json)")
    parser.add_argument("--merged_file", default="", help="path to merged_for_official_eval.json (default: <run_dir>/merged_for_official_eval.json)")
    parser.add_argument("--out_dir", default=str(Path("evals/reports_knowmebench").resolve()))
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    judge_path = Path(args.judge_file) if args.judge_file else (run_dir / "judge_results.json")
    merged_path = Path(args.merged_file) if args.merged_file else (run_dir / "merged_for_official_eval.json")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    judge = _load_json(judge_path)
    merged = _load_json(merged_path)
    output_index = _index_outputs(merged)

    details: List[Dict[str, Any]] = judge.get("details") or []
    meta = judge.get("meta") or {}

    by_task: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    enriched: List[Dict[str, Any]] = []
    for d in details:
        task_type = _safe_str(d.get("task_type")).strip()
        try:
            item_id = int(d.get("id"))
        except Exception:
            item_id = -1
        out_item = output_index.get(ItemKey(task_type=task_type, item_id=item_id), {})
        merged_item = {
            **{k: v for k, v in out_item.items() if k in ["id", "task_type", "question", "reference_answer", "model_answer", "meta"]},
            **{k: v for k, v in d.items() if k in ["score", "reasoning", "status"]},
        }
        enriched.append(merged_item)
        if task_type:
            by_task[task_type].append(merged_item)

    def _score_value(x: Any) -> Optional[float]:
        try:
            return float(x)
        except Exception:
            return None

    overall_scores = [_score_value(x.get("score")) for x in enriched if x.get("status") == "success"]
    overall_scores = [s for s in overall_scores if s is not None]
    overall_avg = (sum(overall_scores) / len(overall_scores)) if overall_scores else 0.0

    table_rows: List[Tuple[str, int, int, float, int, int]] = []
    for task, items in sorted(by_task.items(), key=lambda kv: kv[0].lower()):
        scores = [_score_value(x.get("score")) for x in items if x.get("status") == "success"]
        scores = [s for s in scores if s is not None]
        avg = (sum(scores) / len(scores)) if scores else 0.0
        low_n = sum(1 for x in scores if x <= 2)
        high_n = sum(1 for x in scores if x >= 4)
        table_rows.append((task, len(items), len(scores), avg, low_n, high_n))

    enriched_scored = [x for x in enriched if _score_value(x.get("score")) is not None]
    enriched_scored.sort(key=lambda x: (_score_value(x.get("score")) or 0.0, _safe_str(x.get("task_type")), int(x.get("id") or -1)))
    worst = enriched_scored[: min(10, len(enriched_scored))]
    best = list(reversed(enriched_scored[-min(10, len(enriched_scored)) :]))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"report_{ts}.md"
    meta_path = out_dir / f"meta_{ts}.json"

    report_lines: List[str] = []
    report_lines.append("# KnowMeBench 快速正式评测报告")
    report_lines.append("")
    report_lines.append("## 概览")
    report_lines.append(f"- Run 目录：`{run_dir.as_posix()}`")
    report_lines.append(f"- Judge 模型：`{_safe_str(meta.get('judge_model'))}`")
    report_lines.append(f"- 总题数：{int(meta.get('total_items') or len(details))}")
    report_lines.append(f"- 评估题数：{int(meta.get('evaluated_items') or len(overall_scores))}")
    report_lines.append(f"- 平均分：{float(meta.get('average_score') or overall_avg):.2f} / 5.0")
    report_lines.append("")
    report_lines.append("## 分任务统计")
    report_lines.append(_render_table(table_rows))
    report_lines.append("")

    report_lines.append("## 答得最好的样例（Top）")
    for it in best:
        report_lines.append("")
        report_lines.append(f"### {it.get('task_type')} / ID {it.get('id')} / Score {it.get('score')}")
        report_lines.append("")
        report_lines.append("**Question**")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append(_shorten(_safe_str(it.get("question")), 1200))
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("**Model Answer**")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append(_shorten(_safe_str(it.get("model_answer")), 1200))
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("**Judge Reasoning**")
        report_lines.append("")
        report_lines.append(_shorten(_safe_str(it.get("reasoning")), 800))

    report_lines.append("")
    report_lines.append("## 答得最差的样例（Bottom）")
    for it in worst:
        report_lines.append("")
        report_lines.append(f"### {it.get('task_type')} / ID {it.get('id')} / Score {it.get('score')}")
        report_lines.append("")
        report_lines.append("**Question**")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append(_shorten(_safe_str(it.get("question")), 1200))
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("**Reference Answer**")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append(_shorten(_safe_str(it.get("reference_answer")), 1200))
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("**Model Answer**")
        report_lines.append("")
        report_lines.append("```")
        report_lines.append(_shorten(_safe_str(it.get("model_answer")), 1200))
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("**Judge Reasoning**")
        report_lines.append("")
        report_lines.append(_shorten(_safe_str(it.get("reasoning")), 800))
        m = it.get("meta") or {}
        cs = m.get("context_source")
        if cs:
            report_lines.append("")
            report_lines.append(f"- context_source: `{cs}`")

    report_lines.append("")
    report_lines.append("## 结论与改进建议")
    report_lines.append("")

    overall_label = "优秀" if overall_avg >= 4.2 else ("良好" if overall_avg >= 3.5 else ("一般" if overall_avg >= 2.8 else "偏弱"))
    report_lines.append(f"- 总体结论：本次快速正式评测总体表现为「{overall_label}」，平均分 {overall_avg:.2f}/5。")

    task_sorted = sorted(table_rows, key=lambda r: (r[3], -r[5], r[0]))
    if task_sorted:
        weak = task_sorted[: min(3, len(task_sorted))]
        strong = sorted(table_rows, key=lambda r: (-r[3], -r[5], r[0]))[: min(3, len(table_rows))]
        report_lines.append("- 表现强项：")
        for t, _, _, avg, _, _ in strong:
            report_lines.append(f"  - {t}: {avg:.2f}/5")
        report_lines.append("- 表现短板：")
        for t, _, _, avg, _, _ in weak:
            report_lines.append(f"  - {t}: {avg:.2f}/5")

    report_lines.append("")
    report_lines.append("### 分任务可执行改进")
    for task, items in sorted(by_task.items(), key=lambda kv: kv[0].lower()):
        low = [x for x in items if x.get("status") == "success" and (_score_value(x.get("score")) or 0) <= 2]
        sugg = _suggestions_for_task(task, low)
        if not sugg:
            continue
        report_lines.append(f"- {task}")
        for s in sugg[:6]:
            report_lines.append(f"  - {s}")

    report_path.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")

    meta_out = {
        "timestamp": ts,
        "run_dir": str(run_dir),
        "judge_file": str(judge_path),
        "merged_file": str(merged_path),
        "judge_model": _safe_str(meta.get("judge_model")),
        "total_items": int(meta.get("total_items") or len(details)),
        "evaluated_items": int(meta.get("evaluated_items") or len(overall_scores)),
        "average_score": float(meta.get("average_score") or overall_avg),
        "per_task": [
            {
                "task_type": task,
                "total_items": total_n,
                "evaluated_items": eval_n,
                "average_score": avg,
                "low_score_count": low_n,
                "high_score_count": high_n,
            }
            for task, total_n, eval_n, avg, low_n, high_n in table_rows
        ],
        "report_path": str(report_path),
    }
    meta_path.write_text(json.dumps(meta_out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(report_path))


if __name__ == "__main__":
    main()

