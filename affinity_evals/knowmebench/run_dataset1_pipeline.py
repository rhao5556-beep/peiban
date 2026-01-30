import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--help", action="store_true")
    args, rest = p.parse_known_args()

    if args.help:
        target = Path(__file__).resolve().parents[2] / "evals" / "run_knowmebench_dataset1_pipeline.py"
        cmd = [sys.executable, str(target), "--help"]
        return subprocess.call(cmd)

    target = Path(__file__).resolve().parents[2] / "evals" / "run_knowmebench_dataset1_pipeline.py"
    cmd = [sys.executable, str(target)] + rest
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

