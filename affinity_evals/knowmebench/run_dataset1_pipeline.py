import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend_base_url", default=None)
    p.add_argument("--dataset_dir", default=None)
    p.add_argument("--output_dir", default=None)
    p.add_argument("--mode", choices=["graph_only", "hybrid"], default=None)
    p.add_argument("--user_id", default=None)
    p.add_argument("--limit_samples", type=int, default=0)
    p.add_argument("--limit_per_task", type=int, default=0)
    p.add_argument("--context_window", type=int, default=None)
    p.add_argument("--concurrency", type=int, default=None)
    p.add_argument("--request_timeout_s", type=float, default=None)
    p.add_argument("--task", action="append", default=[])
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "evals" / "run_knowmebench_dataset1_pipeline.py"
    if not target.exists():
        raise RuntimeError(f"missing_target_script: {target}")

    cmd = [sys.executable, str(target)]
    if args.backend_base_url:
        cmd += ["--backend_base_url", args.backend_base_url]
    if args.dataset_dir:
        cmd += ["--dataset_dir", args.dataset_dir]
    if args.output_dir:
        cmd += ["--output_dir", args.output_dir]
    if args.mode:
        cmd += ["--mode", args.mode]
    if args.user_id:
        cmd += ["--user_id", args.user_id]
    if args.context_window is not None:
        cmd += ["--context_window", str(args.context_window)]
    if args.concurrency is not None:
        cmd += ["--concurrency", str(args.concurrency)]
    if args.request_timeout_s is not None:
        cmd += ["--request_timeout_s", str(args.request_timeout_s)]

    limit_per_task = int(args.limit_per_task or 0)
    limit_samples = int(args.limit_samples or 0)
    if limit_per_task <= 0 and limit_samples > 0:
        limit_per_task = limit_samples
    if limit_per_task > 0:
        cmd += ["--limit_per_task", str(limit_per_task)]

    for t in args.task:
        if t:
            cmd += ["--task", t]

    proc = subprocess.run(cmd)
    return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())

