import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    code: int
    message: str


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
    except Exception:
        return

    env_path = Path(__file__).parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)


def _env_flag(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def _first_env(*names: str) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _print_config(
    backend_base_url: str,
    require_judge: bool,
    judge_api_base: Optional[str],
    judge_model: Optional[str],
    judge_api_key: Optional[str],
) -> None:
    print("Eval Env Check")
    print(f"- backend_base_url: {backend_base_url}")
    print(f"- require_judge: {str(bool(require_judge)).lower()}")
    print(f"- judge_api_base: {judge_api_base or ''}")
    print(f"- judge_model: {judge_model or ''}")
    print(f"- judge_api_key_set: {str(bool(judge_api_key)).lower()}")


def _check_backend(backend_base_url: str, timeout_s: float) -> CheckResult:
    try:
        import requests  # type: ignore[import-not-found]
    except Exception as e:
        return CheckResult(False, 50, f"missing_dependency: requests: {e}")

    url = urljoin(backend_base_url.rstrip("/") + "/", "health")
    try:
        resp = requests.get(url, timeout=float(timeout_s))
    except requests.Timeout:
        return CheckResult(False, 40, f"backend_timeout: {url}")
    except requests.RequestException as e:
        return CheckResult(False, 40, f"backend_network_error: {url}: {e}")

    if resp.status_code == 200:
        return CheckResult(True, 0, "backend_ok")
    if resp.status_code in {401, 403}:
        return CheckResult(False, 20, f"backend_auth_error: {resp.status_code} {resp.text}")
    if resp.status_code == 404:
        return CheckResult(False, 30, f"backend_not_found: {url}")
    return CheckResult(False, 30, f"backend_bad_status: {resp.status_code} {resp.text}")


def _check_judge(
    api_key: Optional[str],
    api_base: Optional[str],
    model: Optional[str],
    timeout_s: float,
) -> CheckResult:
    try:
        import requests  # type: ignore[import-not-found]
    except Exception as e:
        return CheckResult(False, 50, f"missing_dependency: requests: {e}")

    if not api_base:
        return CheckResult(False, 30, "judge_api_base_missing")
    if not api_key:
        return CheckResult(False, 10, "judge_api_key_missing")
    if not model:
        return CheckResult(False, 30, "judge_model_missing")

    url = urljoin(api_base.rstrip("/") + "/", "chat/completions")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0.0,
        "max_tokens": 4,
    }
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(timeout_s),
        )
    except requests.Timeout:
        return CheckResult(False, 40, f"judge_timeout: {url}")
    except requests.RequestException as e:
        return CheckResult(False, 40, f"judge_network_error: {url}: {e}")

    if resp.status_code in {401, 403}:
        return CheckResult(False, 20, f"judge_auth_error: {resp.status_code} {resp.text}")
    if resp.status_code == 404:
        return CheckResult(False, 30, f"judge_not_found: {url}")
    if resp.status_code >= 400:
        return CheckResult(False, 30, f"judge_bad_status: {resp.status_code} {resp.text}")

    try:
        _ = resp.json()
    except Exception:
        return CheckResult(False, 30, f"judge_non_json_response: {resp.text}")
    return CheckResult(True, 0, "judge_ok")


def run_check(
    backend_base_url: str,
    require_judge: bool,
    skip_judge_probe: bool,
    timeout_s: float,
) -> int:
    judge_api_key = _first_env("AFFINITY_EVAL_OPENAI_API_KEY", "OPENAI_API_KEY")
    judge_api_base = _first_env(
        "AFFINITY_EVAL_OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "OPENAI_BASE_URL",
    )
    judge_model = _first_env("AFFINITY_EVAL_JUDGE_MODEL", "OPENAI_MODEL")

    _print_config(
        backend_base_url=backend_base_url,
        require_judge=require_judge,
        judge_api_base=judge_api_base,
        judge_model=judge_model,
        judge_api_key=judge_api_key,
    )

    backend_result = _check_backend(backend_base_url, timeout_s=timeout_s)
    if not backend_result.ok:
        print(f"FAIL {backend_result.code}: {backend_result.message}")
        return int(backend_result.code)
    print("PASS backend")

    if skip_judge_probe:
        print("PASS judge (skipped)")
        print("PASS")
        return 0

    if require_judge:
        judge_result = _check_judge(
            api_key=judge_api_key,
            api_base=judge_api_base,
            model=judge_model,
            timeout_s=timeout_s,
        )
        if not judge_result.ok:
            print(f"FAIL {judge_result.code}: {judge_result.message}")
            return int(judge_result.code)
        print("PASS judge")
        print("PASS")
        return 0

    if judge_api_key and judge_api_base and judge_model:
        judge_result = _check_judge(
            api_key=judge_api_key,
            api_base=judge_api_base,
            model=judge_model,
            timeout_s=timeout_s,
        )
        if judge_result.ok:
            print("PASS judge")
        else:
            print(f"WARN judge_probe_failed {judge_result.code}: {judge_result.message}")

    print("PASS")
    return 0


def main() -> int:
    _load_dotenv_if_available()

    p = argparse.ArgumentParser(description="Environment pre-check for eval pipelines")
    p.add_argument(
        "--backend_base_url",
        default=os.environ.get("AFFINITY_EVAL_BACKEND_BASE_URL", "http://localhost:8000"),
    )
    p.add_argument("--require_judge", action="store_true", default=False)
    p.add_argument("--skip_judge_probe", action="store_true", default=False)
    p.add_argument("--timeout_s", type=float, default=10.0)
    args = p.parse_args()

    require_judge = bool(args.require_judge) or _env_flag("AFFINITY_EVAL_ENABLE_JUDGE")
    return run_check(
        backend_base_url=str(args.backend_base_url),
        require_judge=require_judge,
        skip_judge_probe=bool(args.skip_judge_probe),
        timeout_s=float(args.timeout_s),
    )


if __name__ == "__main__":
    sys.exit(main())

