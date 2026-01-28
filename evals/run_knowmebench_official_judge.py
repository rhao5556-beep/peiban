import argparse
import os
import runpy
import sys
from pathlib import Path


def _maybe_load_dotenv(paths) -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    for p in paths:
        if p.exists():
            load_dotenv(p, override=False)


def _find_latest_output_dir(root: Path) -> Path:
    base = root / "outputs" / "knowmebench_run"
    dirs = [p for p in base.glob("ds1_pipeline_*") if p.is_dir()]
    if not dirs:
        raise RuntimeError(f"no_output_dir_found under {base}")
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    p = argparse.ArgumentParser()
    p.add_argument("--input_file", default="", help="Path to merged_for_official_eval.json (default: latest output dir)")
    p.add_argument("--output_file", default="", help="Path to save official_eval_results.json (default: alongside input)")
    p.add_argument("--judge_model", default=os.environ.get("AFFINITY_EVAL_JUDGE_MODEL", "Pro/deepseek-ai/DeepSeek-V3.2"))
    p.add_argument("--api_base", default=os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "https://api.siliconflow.cn/v1")
    p.add_argument("--timeout_s", type=float, default=float(os.environ.get("AFFINITY_EVAL_JUDGE_TIMEOUT_S", "180")))
    p.add_argument("--max_retries", type=int, default=int(os.environ.get("AFFINITY_EVAL_JUDGE_MAX_RETRIES", "2")))
    p.add_argument("--rate_limit_delay", type=float, default=float(os.environ.get("AFFINITY_EVAL_JUDGE_RATE_LIMIT_DELAY", "0.1")))
    args = p.parse_args()

    _maybe_load_dotenv([root / "evals" / ".env.local", root / "evals" / ".env.example", root / "backend" / ".env", root / ".env"])

    if not os.environ.get("OPENAI_API_KEY"):
        if os.environ.get("AFFINITY_EVAL_OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.environ["AFFINITY_EVAL_OPENAI_API_KEY"]

    if not os.environ.get("OPENAI_BASE_URL"):
        if os.environ.get("AFFINITY_EVAL_OPENAI_BASE_URL"):
            os.environ["OPENAI_BASE_URL"] = os.environ["AFFINITY_EVAL_OPENAI_BASE_URL"]
        elif os.environ.get("OPENAI_API_BASE"):
            os.environ["OPENAI_BASE_URL"] = os.environ["OPENAI_API_BASE"]

    if not os.environ.get("OPENAI_API_KEY"):
        print("NO_OPENAI_API_KEY")
        return 3

    out_dir = _find_latest_output_dir(root)
    in_path = Path(args.input_file) if args.input_file else (out_dir / "merged_for_official_eval.json")
    if not in_path.exists():
        raise RuntimeError(f"input_file_not_found: {in_path}")

    out_path = Path(args.output_file) if args.output_file else (in_path.parent / "official_eval_results.json")

    eval_dir = root / "external" / "KnowMeBench" / "evaluate"
    os.chdir(eval_dir)

    sys.argv = [
        "run_eval.py",
        "--input_file",
        str(in_path),
        "--output_file",
        str(out_path),
        "--judge_model",
        args.judge_model,
        "--api_base",
        args.api_base,
        "--timeout_s",
        str(args.timeout_s),
        "--max_retries",
        str(args.max_retries),
        "--rate_limit_delay",
        str(args.rate_limit_delay),
    ]
    runpy.run_path(str(eval_dir / "run_eval.py"), run_name="__main__")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

