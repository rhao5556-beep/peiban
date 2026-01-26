import os
import time

import httpx
import pytest


VITE_BASE_URL = os.getenv("AFFINITY_VITE_URL", "http://localhost:5175").rstrip("/")
API_BASE_URL = os.getenv("AFFINITY_API_URL", "http://localhost:8000").rstrip("/")


def _get_token_via_vite() -> str:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        resp = client.post(f"{VITE_BASE_URL}/api/v1/auth/token", json={})
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token") or ""
        assert token
        return token


@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", "/api/v1/proactive/messages?status=pending"),
        ("GET", "/api/v1/graph/?day=30"),
        ("GET", "/api/v1/affinity/history"),
        ("GET", "/api/v1/content/recommendations"),
        ("GET", "/api/v1/memes/preferences"),
    ],
)
def test_proxy_endpoints_ok(method: str, url: str):
    token = _get_token_via_vite()
    headers = {"Authorization": f"Bearer {token}"}
    budgets_ms = {
        "/api/v1/graph/?day=30": 12000,
    }
    budget_ms = budgets_ms.get(url, 5000)

    start = time.perf_counter()
    with httpx.Client(timeout=30.0, trust_env=False) as client:
        resp = client.request(method, f"{VITE_BASE_URL}{url}", headers=headers)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < budget_ms


@pytest.mark.parametrize(
    "url,expected_status",
    [
        ("/api/v1/proactive/messages?limit=0", 422),
        ("/api/v1/proactive/messages?limit=51", 422),
    ],
)
def test_proactive_messages_limit_validation(url: str, expected_status: int):
    token = _get_token_via_vite()
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        resp = client.get(f"{VITE_BASE_URL}{url}", headers=headers)
    assert resp.status_code == expected_status


def test_proactive_messages_requires_auth():
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        resp = client.get(f"{VITE_BASE_URL}/api/v1/proactive/messages?status=pending")
    assert resp.status_code in (401, 403)


def test_auth_token_direct_backend_ok():
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        resp = client.post(f"{API_BASE_URL}/api/v1/auth/token", json={})
    assert resp.status_code == 200
