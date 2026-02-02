"""
Complete LoCoMo Evaluation Pipeline
完整的 LoCoMo 评测流程（Python 版本）
"""
import argparse
import json
import os
import subprocess
import sys
import time
import threading
import queue
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


def probe_conversation(backend_url: str) -> bool:
    try:
        token_resp = requests.post(
            f"{backend_url.rstrip('/')}/api/v1/auth/token",
            json={},
            timeout=5,
        )
        token_resp.raise_for_status()
        token = (token_resp.json() or {}).get("access_token")
        if not token:
            print("ERROR: probe failed: missing access_token")
            return False

        msg_resp = requests.post(
            f"{backend_url.rstrip('/')}/api/v1/conversation/message",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "LoCoMo probe", "mode": "graph_only", "eval_mode": True},
            timeout=20,
        )
        msg_resp.raise_for_status()
        payload = msg_resp.json() or {}
        if "reply" not in payload:
            print("ERROR: probe failed: missing reply field")
            return False
        print(f"Probe OK: reply_len={len(str(payload.get('reply') or ''))} mode={payload.get('mode')}")
        return True
    except Exception as e:
        print(f"ERROR: probe failed: {e}")
        return False


def run_evaluation(
    backend_url: str,
    dataset_path: Path,
    output_dir: Path,
    mode: str,
    limit_conversations: int,
    limit_questions: int,
    categories: list[int],
    limit_per_category: int,
    inactivity_timeout_s: float,
    total_timeout_s: float,
) -> Optional[Path]:
    """Run LoCoMo evaluation"""
    print("[1/4] Running LoCoMo evaluation...")
    
    # Use the correct path to the evaluation script
    script_dir = Path(__file__).parent.parent  # Go up to project root
    eval_script = script_dir / "affinity_evals" / "locomo" / "run_locomo.py"
    if not eval_script.exists():
        cache_tag = getattr(getattr(sys, "implementation", None), "cache_tag", None)
        if cache_tag:
            pyc_path = eval_script.parent / "__pycache__" / f"run_locomo.{cache_tag}.pyc"
            if pyc_path.exists():
                eval_script = pyc_path
    
    cmd = [
        sys.executable,
        "-u",
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
        "--limit_per_category",
        str(limit_per_category),
    ]
    if categories:
        cmd.append("--categories")
        cmd.extend([str(c) for c in categories])
    cmd.extend(["--chunk_size", "64", "--sleep_after_memorize_s", "0.5"])

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    log_path = output_dir / f"locomo_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    last_nonempty_line: Optional[str] = None
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    q: "queue.Queue[Optional[str]]" = queue.Queue()

    def _reader() -> None:
        if proc.stdout is None:
            q.put(None)
            return
        try:
            for line in proc.stdout:
                q.put(line)
        finally:
            q.put(None)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    started = time.perf_counter()
    last_output = started
    last_heartbeat = started
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as f:
            while True:
                try:
                    line = q.get(timeout=0.5)
                except queue.Empty:
                    line = None

                now = time.perf_counter()
                if line:
                    last_output = now
                    f.write(line)
                    f.flush()
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    stripped = line.strip()
                    if stripped:
                        last_nonempty_line = stripped

                if proc.poll() is not None and q.empty():
                    break

                if total_timeout_s > 0 and (now - started) > float(total_timeout_s):
                    print(f"\nERROR: Evaluation exceeded total timeout ({total_timeout_s}s).")
                    print(f"Log: {log_path}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    return None

                if inactivity_timeout_s > 0 and (now - last_output) > float(inactivity_timeout_s):
                    print(f"\nERROR: No evaluation output for {inactivity_timeout_s}s (possible hang).")
                    print(f"Log: {log_path}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    return None

                if (now - last_heartbeat) > 60.0:
                    last_heartbeat = now
                    print(f"[heartbeat] still running... elapsed={int(now-started)}s log={log_path}")
    finally:
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass

    returncode = proc.wait()
    if returncode != 0:
        print(f"ERROR: Evaluation failed (exit_code={returncode}).")
        print(f"Log: {log_path}")
        return None

    if last_nonempty_line and Path(last_nonempty_line).exists():
        return Path(last_nonempty_line)
    
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
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    if result.returncode != 0:
        print(f"ERROR: Scoring failed!")
        print(result.stderr)
        return False
    
    print(result.stdout)
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
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    if result.returncode != 0:
        print(f"Warning: Report generation failed")
        print(result.stderr)
        return False
    
    print(result.stdout)
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
    p.add_argument("--limit_per_category", type=int, default=3)
    p.add_argument("--categories", nargs="*", type=int, default=[1, 2, 3, 4])
    p.add_argument("--eval_inactivity_timeout_s", type=float, default=900.0)
    p.add_argument("--eval_total_timeout_s", type=float, default=10800.0)
    p.add_argument("--skip_probe", action="store_true", help="Skip pre-run conversation probe")
    p.add_argument("--no_llm", action="store_true", help="Disable LLM judge (exact match only)")
    p.add_argument("--skip_env_check", action="store_true", help="Skip environment pre-check")
    p.add_argument("--api_key", default=os.environ.get("OPENAI_API_KEY"), help="API key for LLM judge")
    p.add_argument("--api_base", default=os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1"), help="API base URL")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3"), help="Judge model")
    args = p.parse_args()

    use_llm_for_check = (not args.no_llm) and bool(args.api_key)
    if not args.skip_env_check:
        check_script = Path(__file__).parent / "check_eval_env.py"
        cmd = [
            sys.executable,
            str(check_script),
            "--backend_base_url",
            str(args.backend_url),
            "--timeout_s",
            "10",
        ]
        if use_llm_for_check:
            cmd.append("--require_judge")
        else:
            cmd.append("--skip_judge_probe")
        pre = subprocess.run(cmd, text=True)
        if pre.returncode != 0:
            return int(pre.returncode)
    
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

    if not args.skip_probe:
        print("Pre-run probe...")
        if not probe_conversation(args.backend_url):
            print("ERROR: Probe failed. Abort before running LoCoMo.")
            return 1
        print()
    
    # Configuration
    print("Configuration:")
    print(f"- Backend URL: {args.backend_url}")
    print(f"- Mode: {args.mode}")
    if args.limit_per_category and args.limit_per_category > 0:
        print(f"- Categories: {args.categories}")
        print(f"- Limit per category: {args.limit_per_category}")
    if args.limit_conversations > 0:
        print(f"- Limit conversations: {args.limit_conversations}")
    if args.limit_questions > 0:
        print(f"- Limit questions: {args.limit_questions}")
    print(f"- LLM Judge: {'Disabled' if args.no_llm else 'Enabled'}")
    if not args.no_llm:
        print(f"- Judge Model: {args.model}")
    print()
    
    # Run evaluation
    eval_dir = run_evaluation(
        backend_url=args.backend_url,
        dataset_path=Path(args.dataset_path),
        output_dir=Path(args.output_dir),
        mode=args.mode,
        limit_conversations=args.limit_conversations,
        limit_questions=args.limit_questions,
        categories=[int(x) for x in (args.categories or []) if isinstance(x, int) and x > 0],
        limit_per_category=int(args.limit_per_category or 0),
        inactivity_timeout_s=float(args.eval_inactivity_timeout_s),
        total_timeout_s=float(args.eval_total_timeout_s),
    )
    
    if not eval_dir:
        print("ERROR: Could not find evaluation output directory")
        return 1
    
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
