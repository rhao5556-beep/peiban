"""
Generate human-readable LoCoMo evaluation report
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CATEGORY_NAMES = {
    1: "Factual Recall",
    2: "Temporal Understanding",
    3: "Reasoning & Inference",
    4: "Detailed Understanding",
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def generate_report(
    summary: Dict[str, Any],
    failures: Optional[List[Dict[str, Any]]] = None,
    lang: str = "en",
) -> str:
    """Generate markdown report"""
    
    is_zh = (lang or "").lower().startswith("zh")
    title = "LoCoMo 评测报告" if is_zh else "LoCoMo Evaluation Report"
    overall_title = "总体表现" if is_zh else "Overall Performance"
    by_type_title = "按问题类型表现" if is_zh else "Performance by Question Type"
    by_task_title = "按任务类型表现" if is_zh else "Performance by Task Type"
    failure_title = "错误分析" if is_zh else "Failure Analysis"
    insights_title = "洞察与改进建议" if is_zh else "Insights & Recommendations"
    generated_label = "生成时间" if is_zh else "Generated"
    total_q_label = "题目总数" if is_zh else "Total Questions"
    correct_label = "正确数" if is_zh else "Correct Answers"
    acc_label = "准确率" if is_zh else "Accuracy"
    em_acc_label = "精确匹配准确率" if is_zh else "Exact Match Accuracy"
    conf_label = "平均置信度" if is_zh else "Average Confidence"
    method_label = "评分方式" if is_zh else "Scoring Method"

    lines = [
        f"# {title}",
        "",
        f"**{generated_label}：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## {overall_title}",
        "",
        f"- **{total_q_label}：** {summary.get('total', 0)}",
        f"- **{correct_label}：** {summary.get('correct', 0)}",
        f"- **{acc_label}：** {summary.get('accuracy', 0.0):.2%}",
        f"- **{em_acc_label}：** {summary.get('exact_match_accuracy', 0.0):.2%}",
        f"- **{conf_label}：** {summary.get('avg_confidence', 0.0):.2f}",
        f"- **{method_label}：** {summary.get('scoring_method', 'unknown')}",
        "",
    ]
    
    # Performance by category
    by_cat = summary.get("by_category", {})
    if by_cat:
        lines.extend([
            f"## {by_type_title}",
            "",
            "| Category | Type | Total | Correct | Accuracy | Exact Match | Confidence |" if not is_zh else "| 类别 | 类型 | 总数 | 正确 | 准确率 | 精确匹配 | 置信度 |",
            "|----------|------|-------|---------|----------|-------------|------------|",
        ])
        
        for cat_id in sorted(by_cat.keys()):
            cat_data = by_cat[cat_id]
            cat_name = cat_data.get("category_name", "Unknown")
            total = cat_data.get("total", 0)
            correct = cat_data.get("correct", 0)
            acc = cat_data.get("accuracy", 0.0)
            exact_acc = cat_data.get("exact_match_accuracy", 0.0)
            conf = cat_data.get("avg_confidence", 0.0)
            
            lines.append(
                f"| {cat_id} | {cat_name} | {total} | {correct} | {acc:.2%} | {exact_acc:.2%} | {conf:.2f} |"
            )
        
        lines.append("")
    
    # Category descriptions
    lines.extend([
        "### Question Type Descriptions" if not is_zh else "### 问题类型说明",
        "",
        "- **Category 1（事实回忆）：** 对话历史中的直接事实" if is_zh else "- **Category 1 (Factual Recall):** Direct facts from conversation history",
        "- **Category 2（时间理解）：** 时间相关信息与日期" if is_zh else "- **Category 2 (Temporal Understanding):** Time-related information and dates",
        "- **Category 3（推理与归纳）：** 需要超越显式事实的推理" if is_zh else "- **Category 3 (Reasoning & Inference):** Requires reasoning beyond explicit facts",
        "- **Category 4（细节理解）：** 对上下文的细节性理解" if is_zh else "- **Category 4 (Detailed Understanding):** Detailed comprehension of context",
        "",
    ])
    
    # Performance by task type
    by_task = summary.get("by_task_type", {})
    if by_task:
        lines.extend([
            f"## {by_task_title}",
            "",
            "| Task Type | Total | Correct | Accuracy | Exact Match | Confidence |" if not is_zh else "| 任务类型 | 总数 | 正确 | 准确率 | 精确匹配 | 置信度 |",
            "|-----------|-------|---------|----------|-------------|------------|",
        ])
        
        for task_type in sorted(by_task.keys()):
            task_data = by_task[task_type]
            total = task_data.get("total", 0)
            correct = task_data.get("correct", 0)
            acc = task_data.get("accuracy", 0.0)
            exact_acc = task_data.get("exact_match_accuracy", 0.0)
            conf = task_data.get("avg_confidence", 0.0)
            
            lines.append(
                f"| {task_type} | {total} | {correct} | {acc:.2%} | {exact_acc:.2%} | {conf:.2f} |"
            )
        
        lines.append("")
    
    # Failure analysis
    if failures:
        lines.extend([
            f"## {failure_title}",
            "",
            f"**失败总数：** {len(failures)}" if is_zh else f"**Total Failures:** {len(failures)}",
            "",
        ])
        
        # Group failures by category
        failures_by_cat: Dict[str, List[Dict[str, Any]]] = {}
        for f in failures:
            cat = str(f.get("category", "unknown"))
            failures_by_cat.setdefault(cat, []).append(f)
        
        for cat_id in sorted(failures_by_cat.keys()):
            cat_name = CATEGORY_NAMES.get(int(cat_id), "Unknown") if cat_id.isdigit() else "Unknown"
            cat_failures = failures_by_cat[cat_id]
            
            lines.extend([
                f"### {cat_name} (Category {cat_id})",
                "",
                f"**Failures:** {len(cat_failures)}",
                "",
            ])
            
            # Show first 5 failures as examples
            for i, f in enumerate(cat_failures[:5]):
                lines.extend([
                    f"#### 示例 {i+1}（ID: {f.get('id')}）" if is_zh else f"#### Example {i+1} (ID: {f.get('id')})",
                    "",
                    f"**参考答案：** {f.get('reference_answer', 'N/A')}" if is_zh else f"**Reference:** {f.get('reference_answer', 'N/A')}",
                    "",
                    f"**系统回答：** {f.get('model_answer', 'N/A')}" if is_zh else f"**Model Answer:** {f.get('model_answer', 'N/A')}",
                    "",
                ])
                
                if "reasoning" in f:
                    lines.extend([
                        f"**Judge 理由：** {f.get('reasoning', 'N/A')}" if is_zh else f"**Judge Reasoning:** {f.get('reasoning', 'N/A')}",
                        "",
                    ])
                
                if "exact_match" in f:
                    lines.extend([
                        f"**精确匹配：** {'是' if f.get('exact_match') else '否'}" if is_zh else f"**Exact Match:** {'Yes' if f.get('exact_match') else 'No'}",
                        "",
                    ])
            
            if len(cat_failures) > 5:
                lines.append(f"*... and {len(cat_failures) - 5} more failures in this category*")
                lines.append("")
    
    # Insights and recommendations
    lines.extend([
        f"## {insights_title}",
        "",
    ])
    
    # Analyze performance
    overall_acc = summary.get("accuracy", 0.0)
    exact_match_acc = summary.get("exact_match_accuracy", 0.0)
    
    if overall_acc >= 0.8:
        lines.append("✅ **表现优秀：** 系统展示出较强的长期记忆能力。" if is_zh else "✅ **Excellent Performance:** The system demonstrates strong long-term memory capabilities.")
    elif overall_acc >= 0.6:
        lines.append("⚠️ **表现良好：** 系统记忆能力尚可，但仍有改进空间。" if is_zh else "⚠️ **Good Performance:** The system shows decent memory but has room for improvement.")
    else:
        lines.append("❌ **需要改进：** 系统在长期记忆任务上表现较弱。" if is_zh else "❌ **Needs Improvement:** The system struggles with long-term memory tasks.")
    
    lines.append("")
    
    # LLM vs exact match gap
    if overall_acc > exact_match_acc + 0.05:
        gap = overall_acc - exact_match_acc
        lines.extend([
            f"📊 **LLM Judge 优势：** LLM 评分比精确匹配多识别出 {gap:.1%} 的正确答案，说明系统存在“语义正确但措辞不同”的回答。" if is_zh else f"📊 **LLM Judge Benefit:** LLM scoring found {gap:.1%} more correct answers than exact match, ",
            "" if is_zh else "indicating the system produces semantically correct answers that differ in phrasing.",
            "",
        ])
    
    # Category-specific insights
    if by_cat:
        weakest_cat = min(by_cat.items(), key=lambda x: x[1].get("accuracy", 0.0))
        strongest_cat = max(by_cat.items(), key=lambda x: x[1].get("accuracy", 0.0))
        
        weak_name = weakest_cat[1].get("category_name", "Unknown")
        strong_name = strongest_cat[1].get("category_name", "Unknown")
        weak_acc = weakest_cat[1].get("accuracy", 0.0)
        strong_acc = strongest_cat[1].get("accuracy", 0.0)
        
        lines.extend([
            f"🎯 **最强项：** {strong_name}（准确率 {strong_acc:.1%}）" if is_zh else f"🎯 **Strongest Area:** {strong_name} ({strong_acc:.1%} accuracy)",
            f"🔧 **最弱项：** {weak_name}（准确率 {weak_acc:.1%}）" if is_zh else f"🔧 **Needs Work:** {weak_name} ({weak_acc:.1%} accuracy)",
            "",
        ])
    
    lines.extend([
        "### Recommendations" if not is_zh else "### 建议",
        "",
    ])
    
    # Specific recommendations based on category performance
    if by_cat:
        for cat_id, cat_data in by_cat.items():
            cat_name = cat_data.get("category_name", "Unknown")
            acc = cat_data.get("accuracy", 0.0)
            
            if acc < 0.6:
                if cat_id == "1":
                    lines.append("- **Factual Recall:** Improve entity extraction and graph storage reliability")
                elif cat_id == "2":
                    lines.append("- **Temporal Understanding:** Enhance temporal entity recognition and date normalization")
                elif cat_id == "3":
                    lines.append("- **Reasoning:** Strengthen multi-hop retrieval and inference capabilities")
                elif cat_id == "4":
                    lines.append("- **Detailed Understanding:** Improve context preservation and detail retention")
    
    lines.extend([
        "",
        "---",
        "",
        "*本报告由 LoCoMo 评测流水线自动生成。*" if is_zh else "*This report was generated automatically by the LoCoMo evaluation pipeline.*",
    ])
    
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Generate LoCoMo evaluation report")
    p.add_argument("--summary_path", required=True, help="Path to scoring summary JSON")
    p.add_argument("--failures_path", default="", help="Path to failures JSON")
    p.add_argument("--output_path", required=True, help="Path to save report")
    p.add_argument("--lang", choices=["en", "zh"], default="en", help="Report language")
    args = p.parse_args()
    
    summary = _load_json(Path(args.summary_path))
    
    failures = None
    if args.failures_path:
        failures_path = Path(args.failures_path)
        if failures_path.exists():
            failures = _load_json(failures_path)
    
    report = generate_report(summary, failures, lang=args.lang)
    
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    
    print(f"Report generated: {output_path}")
    print("\n" + "="*60)
    print(report)


if __name__ == "__main__":
    main()
