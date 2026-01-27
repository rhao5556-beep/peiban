import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_dir", action="append", default=[], help="Existing run dir (can be repeated)")
    parser.add_argument("--mode", default="graph_only")
    parser.add_argument("--output_dir", default=str(Path("outputs/knowmebench_run").resolve()))
    args = parser.parse_args()

    run_dirs = [Path(x) for x in (args.run_dir or []) if x]
    if not run_dirs:
        raise SystemExit("missing --run_dir")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) / f"ds1_pipeline_{args.mode}_{ts}_assembled"
    out_dir.mkdir(parents=True, exist_ok=True)

    merged: List[Dict[str, Any]] = []
    tasks: List[Dict[str, Any]] = []
    for d in run_dirs:
        merged_path = d / "merged_for_official_eval.json"
        if not merged_path.exists():
            raise SystemExit(f"missing merged_for_official_eval.json in {d}")
        items = _load_json(merged_path)
        if not isinstance(items, list):
            raise SystemExit(f"invalid merged json in {d}")
        merged.extend(items)

        run_summaries = sorted(d.glob("knowmebench.dataset1.*.run_summary.json"))
        if run_summaries:
            rs = _load_json(run_summaries[-1])
            for t in rs.get("tasks") or []:
                if isinstance(t, dict):
                    tasks.append(t)

        for f in d.glob("knowmebench.dataset1.*.model_outputs.json"):
            target = out_dir / f.name
            if not target.exists():
                target.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    merged_file = out_dir / "merged_for_official_eval.json"
    _write_json(merged_file, merged)

    summary = {
        "mode": args.mode,
        "timestamp": ts,
        "assembled_from": [str(d) for d in run_dirs],
        "tasks": tasks,
        "merged_file": str(merged_file),
    }
    _write_json(out_dir / f"knowmebench.dataset1.{ts}.run_summary.json", summary)
    print(str(out_dir))


if __name__ == "__main__":
    main()

