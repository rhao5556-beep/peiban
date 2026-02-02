import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


_REL_TIME_RE = re.compile(r"\b(yesterday|today|tomorrow|last\s+\w+|next\s+\w+)\b", flags=re.IGNORECASE)
_NO_INFO_RE = re.compile(r"\b(don't have|doesn't contain|not in.*context|i don't know|不记得|没有提及|无法确定)\b", flags=re.IGNORECASE)
_FABRICATE_RE = re.compile(r"\b(fabricat|hallucin|made up|invented|编造|杜撰)\b", flags=re.IGNORECASE)
_CONTRADICT_RE = re.compile(r"\b(contradic|inconsistent|oppos|与参考相反|矛盾)\b", flags=re.IGNORECASE)
_MISSING_RE = re.compile(r"\b(missing key|fails to recall|did not recall|遗漏|漏掉|关键事实)\b", flags=re.IGNORECASE)
_GENERIC_RE = re.compile(r"\b(generic|vague|hand-wave|空泛|泛化)\b", flags=re.IGNORECASE)
_FORMAT_RE = re.compile(r"\b(format|json|structure|未按|格式)\b", flags=re.IGNORECASE)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _format_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _locomo_reason(item: Dict[str, Any]) -> str:
    cat = item.get("category")
    ref = str(item.get("reference_answer") or "")
    pred = str(item.get("model_answer") or "")

    if isinstance(cat, int) and cat == 2 and _REL_TIME_RE.search(pred) and re.search(r"\d{4}|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", ref, flags=re.IGNORECASE):
        return "相对时间未归一化为绝对日期"
    if _NO_INFO_RE.search(pred):
        return "上下文/检索不足导致拒答或不确定"
    if ref and pred and ref.strip().lower() in pred.strip().lower() and pred.strip().lower() != ref.strip().lower():
        return "精确匹配评分过严（语义接近但表述更长）"
    if ref and pred and pred.strip() != ref.strip():
        return "答案格式不一致（多余解释/同义改写）"
    return "其他"


def _km_reason(d: Dict[str, Any]) -> str:
    score = int(d.get("score") or 0)
    reasoning = str(d.get("reasoning") or "")
    if score >= 4:
        return "高分"
    if _FABRICATE_RE.search(reasoning):
        return "编造/无中生有"
    if _CONTRADICT_RE.search(reasoning):
        return "与参考答案矛盾"
    if _MISSING_RE.search(reasoning):
        return "漏掉关键事实/证据点"
    if _GENERIC_RE.search(reasoning):
        return "回答泛化、缺少针对性证据"
    if _FORMAT_RE.search(reasoning):
        return "输出格式/结构不符合预期"
    if "insufficient" in reasoning.lower() or "no evidence" in reasoning.lower():
        return "证据不足仍作答（应拒答或澄清）"
    return "其他"


def summarize_locomo(locomo_dir: Path) -> Tuple[str, Dict[str, Any]]:
    summary_path = locomo_dir / "scoring_summary.json"
    failures_path = locomo_dir / "failures.json"
    model_outputs_path = None
    for p in locomo_dir.glob("*.model_outputs.json"):
        model_outputs_path = p
        break

    summary = _load_json(summary_path) if summary_path.exists() else {}
    failures = _load_json(failures_path) if failures_path.exists() else []
    outputs = _load_json(model_outputs_path) if model_outputs_path and model_outputs_path.exists() else []

    by_cat = summary.get("by_category") or {}
    reason_counter = Counter()
    cat_reason = defaultdict(Counter)
    sample_by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for f in failures if isinstance(failures, list) else []:
        r = _locomo_reason(f)
        reason_counter[r] += 1
        c = str(f.get("category") if f.get("category") is not None else "unknown")
        cat_reason[c][r] += 1
        if len(sample_by_cat[c]) < 2:
            sample_by_cat[c].append(f)

    lines: List[str] = []
    lines.append("## LoCoMo（每类 3 题，共 12 题）")
    lines.append("")
    lines.append(f"- 输出目录：{locomo_dir}")
    lines.append(
        f"- 总题数：{summary.get('total', 0)}，正确：{summary.get('correct', 0)}，准确率：{_format_pct(float(summary.get('accuracy', 0.0) or 0.0))}"
    )
    lines.append(f"- 评分方式：{summary.get('scoring_method', '')}（当前为精确匹配，偏严格）")
    lines.append("")
    lines.append("### 按题型丢分情况")
    lines.append("")
    lines.append("| Category | 类型 | 题数 | 准确率 | 主要丢分原因（Top） |")
    lines.append("|---:|---|---:|---:|---|")
    for c in ["1", "2", "3", "4"]:
        d = by_cat.get(c) or {}
        total = int(d.get("total") or 0)
        acc = float(d.get("accuracy") or 0.0)
        top_reason = ""
        if cat_reason.get(c):
            top_reason = ", ".join([f"{k}({v})" for k, v in cat_reason[c].most_common(2)])
        lines.append(f"| {c} | {d.get('category_name','')} | {total} | {_format_pct(acc)} | {top_reason} |")
    lines.append("")
    lines.append("### 失败样例（每类最多 2 条）")
    lines.append("")
    for c in ["1", "2", "3", "4"]:
        if not sample_by_cat.get(c):
            continue
        d = by_cat.get(c) or {}
        lines.append(f"#### Category {c}：{d.get('category_name','')}")
        for ex in sample_by_cat[c]:
            rid = ex.get("id")
            ref = ex.get("reference_answer")
            pred = ex.get("model_answer")
            reason = _locomo_reason(ex)
            lines.append(f"- 题目ID {rid}：参考答案={ref!r}，模型答案={str(pred)[:160]!r}，判因：{reason}")
        lines.append("")

    lines.append("### 修复方案（可执行）")
    lines.append("")
    lines.append("- 将 LoCoMo 评分从精确匹配切换为 LLM Judge 或至少加入“同义/格式归一化”规则（当前 0 分主要来自表述不同而非完全不会）。")
    lines.append("- 对 Temporal（Category 2）：强制输出绝对日期（ISO 或明确年月日），并在上下文里注入 session 日期时间；必要时加入后处理把 yesterday/last week 基于 session time 归一化。")
    lines.append("- 对 Factual/Detailed：提示词要求“只输出答案本体，不要解释”，避免精确匹配被多余解释击穿。")
    lines.append("- 增加 AnswerPolicy 策略层（严格事实/推理两种模式），评测时显式使用 strict_factual：")
    lines.append("  - build_prompt 支持注入 context_time（对话发生时间），并要求把 yesterday/last week 等相对时间转换为基于该日期的绝对时间")
    lines.append("  - postprocess 清理“根据对话记录/答案是/最终答案”等前缀、去除末尾标点/引号，保证 exact_match 友好")
    lines.append("  - select_answer_policy 支持 mode 显式指定 +（可选）基于 who/what/when/where 等规则自动选择")

    return "\n".join(lines), {"summary": summary, "failures": failures, "outputs": outputs}


def summarize_knowmebench(km_dir: Path) -> Tuple[str, Dict[str, Any]]:
    judge_path = km_dir / "judge_results.json"
    judge = _load_json(judge_path) if judge_path.exists() else {}
    details = judge.get("details") or []

    by_task: Dict[str, List[int]] = defaultdict(list)
    by_task_samples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_task_reasons: Dict[str, Counter] = defaultdict(Counter)
    for d in details if isinstance(details, list) else []:
        t = str(d.get("task_type") or "unknown")
        s = int(d.get("score") or 0)
        by_task[t].append(s)
        if s <= 2:
            by_task_reasons[t][_km_reason(d)] += 1
        if s <= 2 and len(by_task_samples[t]) < 2:
            by_task_samples[t].append(d)

    lines: List[str] = []
    lines.append("## KnowMeBench Dataset1（7 类任务每类 3 题，共 21 题）")
    lines.append("")
    lines.append(f"- 输出目录：{km_dir}")
    meta = judge.get("meta") or {}
    lines.append(f"- Judge 模型：{meta.get('judge_model','')}")
    lines.append(f"- 平均分：{float(meta.get('average_score') or 0.0):.2f} / 5.0（评测条目 {meta.get('evaluated_items',0)}/{meta.get('total_items',0)}）")
    lines.append("")
    lines.append("### 按任务类型得分")
    lines.append("")
    lines.append("| 任务类型 | 题数 | 平均分 | 低分样例（≤2分） |")
    lines.append("|---|---:|---:|---|")
    for task_type in sorted(by_task.keys()):
        scores = by_task[task_type]
        avg = (sum(scores) / len(scores)) if scores else 0.0
        samples = by_task_samples.get(task_type) or []
        sample_text = ""
        if samples:
            sample_text = "；".join([f"id={s.get('id')} score={s.get('score')} {str(s.get('reasoning') or '')[:60]}" for s in samples])
        lines.append(f"| {task_type} | {len(scores)} | {avg:.2f} | {sample_text} |")
    lines.append("")
    lines.append("### 按任务类型丢分原因（仅统计 ≤2 分样本）")
    lines.append("")
    lines.append("| 任务类型 | 低分题数 | 主要丢分原因（Top） |")
    lines.append("|---|---:|---|")
    for task_type in sorted(by_task.keys()):
        c = by_task_reasons.get(task_type) or Counter()
        low_n = sum(int(v) for v in c.values())
        top = ""
        if low_n:
            top = ", ".join([f"{k}({v})" for k, v in c.most_common(3)])
        lines.append(f"| {task_type} | {low_n} | {top} |")
    lines.append("")
    lines.append("### 修复方案（按常见低分模式）")
    lines.append("")
    lines.append("- Information Extraction：增加结构化输出约束（JSON/要点列表），并在后端检索上下文中保证关键字段可见，避免漏抽/多抽。")
    lines.append("- Adversarial Abstention：加入“是否有证据支撑”的自检步骤；无证据时明确拒答，避免被判 0 分编造。")
    lines.append("- Temporal Reasoning：统一时间格式（ISO/明确年月日）并在提示词中要求计算过程与最终答案分离。")
    lines.append("- Ordering/Analysis 类：提示词要求给出排序依据或触发线索，避免只给结论导致被判理由不足。")
    lines.append("- Psychoanalysis/Mind-Body：加强对矛盾点的显式引用（来自记录片段的证据句），减少泛化心理分析。")

    return "\n".join(lines), {"judge": judge}


def _nth_subdir(root: Path, prefix: str, n: int) -> Path | None:
    if not root.exists():
        return None
    subs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)]
    if not subs:
        return None
    subs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if n < 0 or n >= len(subs):
        return None
    return subs[n]


def _compare_locomo(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    a_sum = a.get("summary") or {}
    b_sum = b.get("summary") or {}
    a_acc = float(a_sum.get("accuracy") or 0.0)
    b_acc = float(b_sum.get("accuracy") or 0.0)
    a_total = int(a_sum.get("total") or 0)
    b_total = int(b_sum.get("total") or 0)
    delta = a_acc - b_acc
    return f"- LoCoMo：准确率 {_format_pct(b_acc)} → {_format_pct(a_acc)}（Δ{_format_pct(delta)}），题量 {b_total}→{a_total}"


def _compare_km(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    a_j = a.get("judge") or {}
    b_j = b.get("judge") or {}
    a_meta = a_j.get("meta") or {}
    b_meta = b_j.get("meta") or {}
    a_avg = float(a_meta.get("average_score") or 0.0)
    b_avg = float(b_meta.get("average_score") or 0.0)
    delta = a_avg - b_avg
    return f"- KnowMeBench：平均分 {b_avg:.2f} → {a_avg:.2f}（Δ{delta:+.2f}）"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--locomo_dir", default="")
    p.add_argument("--knowmebench_dir", default="")
    p.add_argument("--baseline_locomo_dir", default="")
    p.add_argument("--baseline_knowmebench_dir", default="")
    p.add_argument("--out_path", required=True)
    args = p.parse_args()

    project_root = Path(__file__).parent.parent
    locomo_root = project_root / "outputs" / "locomo_run"
    km_root = project_root / "outputs" / "knowmebench_run"

    locomo_dir = Path(args.locomo_dir) if args.locomo_dir else (_nth_subdir(locomo_root, "locomo10_", 0) or locomo_root)
    km_dir = Path(args.knowmebench_dir) if args.knowmebench_dir else (_nth_subdir(km_root, "ds1_pipeline_", 0) or km_root)
    out_path = Path(args.out_path)

    locomo_md, locomo_obj = summarize_locomo(locomo_dir)
    km_md, km_obj = summarize_knowmebench(km_dir)

    baseline_locomo_dir = Path(args.baseline_locomo_dir) if args.baseline_locomo_dir else (_nth_subdir(locomo_root, "locomo10_", 1))
    baseline_km_dir = Path(args.baseline_knowmebench_dir) if args.baseline_knowmebench_dir else (_nth_subdir(km_root, "ds1_pipeline_", 1))

    compare_lines: List[str] = []
    if baseline_locomo_dir and baseline_locomo_dir.exists():
        _, base_obj = summarize_locomo(baseline_locomo_dir)
        compare_lines.append(_compare_locomo(locomo_obj, base_obj))
    if baseline_km_dir and baseline_km_dir.exists():
        _, base_obj = summarize_knowmebench(baseline_km_dir)
        compare_lines.append(_compare_km(km_obj, base_obj))

    content = "\n".join(
        [
            "# 评测中文总结（LoCoMo + KnowMeBench）",
            "",
            "## 与上一轮对比",
            "",
            *(compare_lines if compare_lines else ["- 未找到可对比的上一轮输出目录"]),
            "",
            "## 注意事项（下一阶段实现细节）",
            "",
            "- 仅在 eval_mode 下启用 extract_question_text：评测消息含大量上下文，必须先提取 Question:…Answer: 区间再做策略分类；产品态对话不要依赖该格式，避免多问题误抽。",
            "- LoCoMo Temporal 输出必须贴近 reference：具体日期用“D Month YYYY”（如 7 May 2023），问年份只输出 YYYY；避免 ISO 造成 exact_match 误判。",
            "- Temporal 后处理只做确定性归一化：去时刻、ISO→LoCoMo、last year→年份（需 session_time）；不把 last Saturday/last week 强行推断为具体日期，避免引入新编造。",
            "- eval_task_type 仅评测用：只在 eval_mode=true 时透传并用于策略选择映射，避免产品代码依赖 benchmark 标签。",
            "- 目标建议：LoCoMo（12题）向 50-60% 靠近；KnowMeBench（21题）回升到 2.95-3.2。",
            "",
            locomo_md,
            "",
            km_md,
            "",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
