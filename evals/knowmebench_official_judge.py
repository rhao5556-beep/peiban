import runpy
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "affinity_evals" / "knowmebench" / "official_judge.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
