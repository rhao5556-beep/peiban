"""
Complete LoCoMo Evaluation Pipeline
完整的 LoCoMo 评测流程（Python 版本）
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# Load .env.local if exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from: {env_path}")
except ImportError:
    pass  # python-dotenv not installed, use system env vars


def check_backend(backend_url: str) -> bool:
    """Check if backend is running"""
    try:
        response = requests.get(f"{backend_url.rstrip('/')}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def _run_cmd_stream(cmd: list[str]) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env,
    )
    last_nonempty = ""
    assert p.stdout is not None
    for line in p.stdout:
        s = line.rstrip("\n")
        print(s)
        if s.strip():
            last_nonempty = s.strip()
    rc = p.wait()
    return rc, last_nonempty


def run_evaluation(
    backend_url: str,
    dataset_path: Path,
    output_dir: Path,
    mode: str,
    limit_conversations: int,
    limit_questions: int,
) -> Optional[Path]:
    """Run LoCoMo evaluation"""
    print("[1/4] Running LoCoMo evaluation...")
    
    project_root = Path(__file__).parent.parent
    eval_script = project_root / "evals" / "run_locomo10_pipeline.py"
    
    cmd = [
        sys.executable,
        str(eval_script),
        "--backend_base_url",
        backend_url,
        "--dataset_path",
        str(dataset_path),
        "--output_dir",
        str(output_dir),
        "--mode",
        mode,
        "--eval_mode",
        "--limit_conversations",
        str(limit_conversations),
        "--limit_questions",
        str(limit_questions),
        "--sleep_after_memorize_s",
        "0.5",
        "--wait_outbox_done_s",
        "20",
    ]
    
    rc, last_line = _run_cmd_stream(cmd)
    if rc != 0:
        print("ERROR: Evaluation failed!")
        return None
    
    # Parse output to get the directory
    if last_line and Path(last_line).exists():
        return Path(last_line)
    
    # Fallback: find latest directory
    pattern = f"locomo10_{mode}_*"
    dirs = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if dirs:
        return dirs[0]
    
    return None


def find_model_outputs(eval_dir: Path) -> Optional[Path]:
    """Find model outputs file"""
    files = list(eval_dir.glob("*.model_outputs.json"))
    if files:
        return files[0]
    return None


def score_with_llm(
    model_outputs: Path,
    output_dir: Path,
    use_llm: bool,
    api_key: Optional[str],
    api_base: Optional[str],
    model: Optional[str],
) -> bool:
    """Score outputs with LLM judge"""
    print("[2/4] Scoring with LLM judge...")
    
    # Use correct path to scoring script
    script_dir = Path(__file__).parent
    scoring_script = script_dir / "score_locomo_with_llm.py"
    
    cmd = [
        sys.executable,
        str(scoring_script),
        "--in_path", str(model_outputs),
        "--out_path", str(output_dir / "scoring_summary.json"),
        "--failures_out_path", str(output_dir / "failures.json"),
        "--detailed_out_path", str(output_dir / "detailed_scores.json"),
        "--rate_limit_delay", "0.1",
    ]
    
    if use_llm:
        cmd.append("--use_llm")
        if api_key:
            cmd.extend(["--api_key", api_key])
        if api_base:
            cmd.extend(["--api_base", api_base])
        if model:
            cmd.extend(["--model", model])
    else:
        cmd.append("--no_llm")
    
    rc, _ = _run_cmd_stream(cmd)
    if rc != 0:
        print("ERROR: Scoring failed!")
        return False
    return True


def generate_report(
    summary_path: Path,
    failures_path: Path,
    output_path: Path,
) -> bool:
    """Generate evaluation report"""
    print("[3/4] Generating evaluation report...")
    
    # Use correct path to report generator
    script_dir = Path(__file__).parent
    report_script = script_dir / "generate_locomo_report.py"
    
    cmd = [
        sys.executable,
        str(report_script),
        "--summary_path", str(summary_path),
        "--failures_path", str(failures_path),
        "--output_path", str(output_path),
    ]
    
    rc, _ = _run_cmd_stream(cmd)
    if rc != 0:
        print(f"Warning: Report generation failed")
        return False
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Complete LoCoMo Evaluation Pipeline")
    p.add_argument("--backend_url", default="http://localhost:8000", help="Backend URL")
    
    # Fix dataset path to be relative to project root
    project_root = Path(__file__).parent.parent
    default_dataset = str(project_root / "data" / "locomo" / "locomo10.json")
    default_output = str(project_root / "outputs" / "locomo_run")
    
    p.add_argument("--dataset_path", default=default_dataset, help="Dataset path")
    p.add_argument("--output_dir", default=default_output, help="Output directory")
    p.add_argument("--mode", choices=["hybrid", "graph_only"], default="hybrid", help="Retrieval mode")
    p.add_argument("--limit_conversations", type=int, default=0, help="Limit number of conversations (0=all)")
    p.add_argument("--limit_questions", type=int, default=0, help="Limit questions per conversation (0=all)")
    p.add_argument("--score_only", action="store_true", help="Skip stage 1 and only run scoring/report")
    p.add_argument("--eval_dir", default="", help="Existing eval output directory (for --score_only)")
    p.add_argument("--no_llm", action="store_true", help="Disable LLM judge (exact match only)")
    p.add_argument("--api_key", default=os.environ.get("OPENAI_API_KEY"), help="API key for LLM judge")
    p.add_argument("--api_base", default=os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1"), help="API base URL")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3"), help="Judge model")
    args = p.parse_args()
    
    print("="*60)
    print("LoCoMo Evaluation Pipeline")
    print("="*60)
    print()
    
    # Check backend
    print("[0/4] Checking backend status...")
    if not check_backend(args.backend_url):
        print(f"ERROR: Backend is not running at {args.backend_url}")
        print("Please start backend first: cd backend && start-dev.bat")
        return 1
    print("Backend is running ✓")
    print()
    
    # Configuration
    print("Configuration:")
    print(f"- Backend URL: {args.backend_url}")
    print(f"- Mode: {args.mode}")
    if args.limit_conversations > 0:
        print(f"- Limit conversations: {args.limit_conversations}")
    if args.limit_questions > 0:
        print(f"- Limit questions: {args.limit_questions}")
    print(f"- LLM Judge: {'Disabled' if args.no_llm else 'Enabled'}")
    if not args.no_llm:
        print(f"- Judge Model: {args.model}")
    print()
    
    eval_dir: Optional[Path] = None
    if args.score_only:
        if args.eval_dir:
            eval_dir = Path(args.eval_dir)
        else:
            output_dir = Path(args.output_dir)
            pattern = f"locomo10_{args.mode}_*"
            dirs = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            if dirs:
                eval_dir = dirs[0]
        if not eval_dir or not eval_dir.exists():
            print("ERROR: --score_only requires a valid --eval_dir or an existing output directory")
            return 1
        print("[1/4] Skipping LoCoMo evaluation (score_only) ✓")
        print(f"Using output directory: {eval_dir}")
        print()
    else:
        # Run evaluation
        eval_dir = run_evaluation(
            backend_url=args.backend_url,
            dataset_path=Path(args.dataset_path),
            output_dir=Path(args.output_dir),
            mode=args.mode,
            limit_conversations=args.limit_conversations,
            limit_questions=args.limit_questions,
        )
    
    if not eval_dir:
        print("ERROR: Could not find evaluation output directory")
        return 1
    
    if not args.score_only:
        print(f"Evaluation completed ✓")
        print(f"Output directory: {eval_dir}")
        print()
    
    # Find model outputs
    model_outputs = find_model_outputs(eval_dir)
    if not model_outputs:
        print("ERROR: Could not find model outputs file")
        return 1
    
    print(f"Model outputs: {model_outputs}")
    print()
    
    # Score with LLM
    use_llm = not args.no_llm
    if use_llm and not args.api_key:
        print("Warning: No API key provided, falling back to exact match scoring")
        use_llm = False
    
    if not score_with_llm(
        model_outputs=model_outputs,
        output_dir=eval_dir,
        use_llm=use_llm,
        api_key=args.api_key,
        api_base=args.api_base,
        model=args.model,
    ):
        print("ERROR: Scoring failed")
        return 1
    
    print("Scoring completed ✓")
    print()
    
    # Generate report
    summary_path = eval_dir / "scoring_summary.json"
    failures_path = eval_dir / "failures.json"
    report_path = eval_dir / "EVALUATION_REPORT.md"
    
    generate_report(summary_path, failures_path, report_path)
    
    print()
    print("="*60)
    print("Evaluation Complete!")
    print("="*60)
    print()
    print(f"Results saved to: {eval_dir}")
    print("- scoring_summary.json: Overall metrics")
    print("- failures.json: Failed cases")
    print("- detailed_scores.json: All scores with reasoning")
    print("- EVALUATION_REPORT.md: Human-readable report")
    print()
    print("To view results:")
    print(f"  cat {report_path}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
