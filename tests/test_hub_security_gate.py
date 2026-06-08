"""Tests for SecurityGateMiddleware — Origin/Host allowlist + CSRF (TASK-248).

The gate is browser-evidence-gated: it only engages for requests carrying an
Origin/Referer header, so non-browser clients (the default TestClient) pass
through. We exercise the browser path by setting base_url + Origin/Referer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from web.server import create_app  # noqa: E402

_LOCAL = "http://localhost:9188"


@pytest.fixture
def hub_env(tmp_path, monkeypatch):
    """Isolated registry + a fake cwd project so /api/hub/* routes work."""
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_path / "registry.json"))
    cwd_project = tmp_path / "meta"
    (cwd_project / ".coding-os").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(cwd_project))
    monkeypatch.delenv("COS_WEB_CORS_ALLOW_ALL", raising=False)
    monkeypatch.chdir(cwd_project)
    return cwd_project


def _local_client() -> TestClient:
    # base_url localhost → Host header is an allowed localhost name.
    return TestClient(create_app(), base_url=_LOCAL)


class TestOriginAllowlist:
    def test_cross_origin_mutation_rejected(self, hub_env):
        with _local_client() as client:
            resp = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Origin": "http://evil.example.com"},
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["category"] == "forbidden"

    def test_same_origin_mutation_passes(self, hub_env):
        with _local_client() as client:
            resp = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Origin": _LOCAL},
            )
        # Passes the gate → the route runs (200). Never a 403.
        assert resp.status_code == 200, resp.text

    def test_cross_origin_referer_fallback_rejected(self, hub_env):
        with _local_client() as client:
            resp = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Referer": "http://evil.example.com/x"},
            )
        assert resp.status_code == 403, resp.text


class TestDnsRebinding:
    def test_non_local_host_with_browser_evidence_rejected(self, hub_env):
        # Host=testserver (TestClient default base_url) + a browser Origin →
        # the rebinding defense rejects the unexpected Host.
        with TestClient(create_app()) as client:  # base_url http://testserver
            resp = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Origin": _LOCAL},
            )
        assert resp.status_code == 403, resp.text


class TestCsrfDoubleSubmit:
    def test_csrf_cookie_issued_on_response(self, hub_env):
        with _local_client() as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert "cos_csrf" in resp.cookies

    def test_mutation_requires_token_once_cookie_present(self, hub_env):
        with _local_client() as client:
            client.get("/health")  # establishes the cos_csrf cookie
            token = client.cookies.get("cos_csrf")
            assert token
            # Cookie present but no X-CSRF-Token header → rejected.
            bad = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Origin": _LOCAL},
            )
            assert bad.status_code == 403, bad.text
            # Correct echo → passes.
            good = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Origin": _LOCAL, "X-CSRF-Token": token},
            )
            assert good.status_code == 200, good.text


class TestNonBrowserClientUnaffected:
    def test_server_side_mutation_passes_without_headers(self, hub_env):
        # No Origin/Referer (curl/test/server) → not a CSRF vector → passes,
        # proving the gate breaks no existing server-side test.
        with TestClient(create_app()) as client:
            resp = client.post("/api/hub/registry/gc", json={"dry_run": True})
        assert resp.status_code == 200, resp.text


class TestCorsAllowAllEscapeHatch:
    def test_allow_all_disables_gate(self, hub_env, monkeypatch):
        monkeypatch.setenv("COS_WEB_CORS_ALLOW_ALL", "1")
        with _local_client() as client:
            resp = client.post(
                "/api/hub/registry/gc",
                json={"dry_run": True},
                headers={"Origin": "http://evil.example.com"},
            )
        assert resp.status_code == 200, resp.text
