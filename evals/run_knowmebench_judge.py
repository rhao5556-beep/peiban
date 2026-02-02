import argparse
import sys
import importlib.util
from pathlib import Path


def _find_latest_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("ds1_pipeline_")]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", default="")
    p.add_argument("--output_file", default="")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--timeout_s", type=float, default=30.0)
    p.add_argument("--force", action="store_true", default=False)
    args = p.parse_args()

    project_root = Path(__file__).parent.parent
    out_root = project_root / "outputs" / "knowmebench_run"

    input_dir = Path(args.input_dir) if args.input_dir else (_find_latest_dir(out_root) or out_root)
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"input_dir not found: {input_dir}")

    output_file = Path(args.output_file) if args.output_file else (input_dir / "judge_results.json")

    judge_path = project_root / "affinity_evals" / "knowmebench" / "official_judge.py"
    if not judge_path.exists():
        raise SystemExit(f"official_judge.py not found: {judge_path}")
    spec = importlib.util.spec_from_file_location("affinity_official_judge", judge_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"failed to load module from: {judge_path}")
    official_judge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official_judge)

    argv = [
        "official_judge",
        "--input_dir",
        str(input_dir),
        "--output_file",
        str(output_file),
        "--concurrency",
        str(int(args.concurrency)),
        "--timeout_s",
        str(float(args.timeout_s)),
    ]
    if args.force:
        argv.append("--force")

    prev_argv = sys.argv[:]
    try:
        sys.argv = argv
        official_judge.main()
    finally:
        sys.argv = prev_argv


if __name__ == "__main__":
    main()
