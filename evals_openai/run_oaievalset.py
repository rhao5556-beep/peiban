import sys
from pathlib import Path


def _bootstrap() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "external" / "openai-evals"))
    try:
        from dotenv import load_dotenv

        env_path = repo_root / "evals" / ".env.local"
        if env_path.exists():
            load_dotenv(env_path, override=True)
    except Exception:
        pass


def main() -> None:
    _bootstrap()
    from evals.cli.oaievalset import main as _main

    _main()


if __name__ == "__main__":
    main()
