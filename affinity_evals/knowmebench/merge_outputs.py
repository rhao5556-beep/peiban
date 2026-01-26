import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default=str(Path("outputs/knowmebench_run/ds1_graph_only_limit5_all7").resolve()))
    parser.add_argument(
        "--output_file",
        default=str(Path("outputs/knowmebench_run/ds1_graph_only_limit5_all7/merged_for_official_eval.json").resolve()),
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_file = Path(args.output_file)

    files = sorted(input_dir.glob("*.model_outputs.json"))
    if not files:
        raise SystemExit(f"no *.model_outputs.json found under {input_dir}")

    merged = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit(f"invalid format (expected list): {f}")
        merged.extend(data)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"merged_items={len(merged)}")
    print(str(out_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

