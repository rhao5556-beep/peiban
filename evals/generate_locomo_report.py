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
) -> str:
    """Generate markdown report"""
    
    lines = [
        "# LoCoMo Evaluation Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Overall Performance",
        "",
        f"- **Total Questions:** {summary.get('total', 0)}",
        f"- **Correct Answers:** {summary.get('correct', 0)}",
        f"- **Accuracy:** {summary.get('accuracy', 0.0):.2%}",
        f"- **Exact Match Accuracy:** {summary.get('exact_match_accuracy', 0.0):.2%}",
        f"- **Average Confidence:** {summary.get('avg_confidence', 0.0):.2f}",
        f"- **Scoring Method:** {summary.get('scoring_method', 'unknown')}",
        "",
    ]
    
    # Performance by category
    by_cat = summary.get("by_category", {})
    if by_cat:
        lines.extend([
            "## Performance by Question Type",
            "",
            "| Category | Type | Total | Correct | Accuracy | Exact Match | Confidence |",
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
        "### Question Type Descriptions",
        "",
        "- **Category 1 (Factual Recall):** Direct facts from conversation history",
        "- **Category 2 (Temporal Understanding):** Time-related information and dates",
        "- **Category 3 (Reasoning & Inference):** Requires reasoning beyond explicit facts",
        "- **Category 4 (Detailed Understanding):** Detailed comprehension of context",
        "",
    ])
    
    # Performance by task type
    by_task = summary.get("by_task_type", {})
    if by_task:
        lines.extend([
            "## Performance by Task Type",
            "",
            "| Task Type | Total | Correct | Accuracy | Exact Match | Confidence |",
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
            "## Failure Analysis",
            "",
            f"**Total Failures:** {len(failures)}",
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
                    f"#### Example {i+1} (ID: {f.get('id')})",
                    "",
                    f"**Reference:** {f.get('reference_answer', 'N/A')}",
                    "",
                    f"**Model Answer:** {f.get('model_answer', 'N/A')}",
                    "",
                ])
                
                if "reasoning" in f:
                    lines.extend([
                        f"**Judge Reasoning:** {f.get('reasoning', 'N/A')}",
                        "",
                    ])
                
                if "exact_match" in f:
                    lines.extend([
                        f"**Exact Match:** {'Yes' if f.get('exact_match') else 'No'}",
                        "",
                    ])
            
            if len(cat_failures) > 5:
                lines.append(f"*... and {len(cat_failures) - 5} more failures in this category*")
                lines.append("")
    
    # Insights and recommendations
    lines.extend([
        "## Insights & Recommendations",
        "",
    ])
    
    # Analyze performance
    overall_acc = summary.get("accuracy", 0.0)
    exact_match_acc = summary.get("exact_match_accuracy", 0.0)
    
    if overall_acc >= 0.8:
        lines.append("✅ **Excellent Performance:** The system demonstrates strong long-term memory capabilities.")
    elif overall_acc >= 0.6:
        lines.append("⚠️ **Good Performance:** The system shows decent memory but has room for improvement.")
    else:
        lines.append("❌ **Needs Improvement:** The system struggles with long-term memory tasks.")
    
    lines.append("")
    
    # LLM vs exact match gap
    if overall_acc > exact_match_acc + 0.05:
        gap = overall_acc - exact_match_acc
        lines.extend([
            f"📊 **LLM Judge Benefit:** LLM scoring found {gap:.1%} more correct answers than exact match, ",
            "indicating the system produces semantically correct answers that differ in phrasing.",
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
            f"🎯 **Strongest Area:** {strong_name} ({strong_acc:.1%} accuracy)",
            f"🔧 **Needs Work:** {weak_name} ({weak_acc:.1%} accuracy)",
            "",
        ])
    
    lines.extend([
        "### Recommendations",
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
        "*This report was generated automatically by the LoCoMo evaluation pipeline.*",
    ])
    
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Generate LoCoMo evaluation report")
    p.add_argument("--summary_path", required=True, help="Path to scoring summary JSON")
    p.add_argument("--failures_path", default="", help="Path to failures JSON")
    p.add_argument("--output_path", required=True, help="Path to save report")
    args = p.parse_args()
    
    summary = _load_json(Path(args.summary_path))
    
    failures = None
    if args.failures_path:
        failures_path = Path(args.failures_path)
        if failures_path.exists():
            failures = _load_json(failures_path)
    
    report = generate_report(summary, failures)
    
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    
    print(f"Report generated: {output_path}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
