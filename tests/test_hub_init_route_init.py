"""TASK-249 — GET /api/hub/stacks + POST /api/hub/registry/init (create-from-UI).

The real scaffold is covered by tests/test_cli.py; here we cover the data-driven
stack list and the route's validation + cleanup contract with _run_cos_init mocked.
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

from web.server import create_app

_LOCAL = "http://localhost:9188"


@pytest.fixture
def hub_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.delenv("COS_WEB_CORS_ALLOW_ALL", raising=False)
    return tmp_path


def _client() -> TestClient:
    # localhost base_url so the security gate's Host check passes for mutations.
    return TestClient(create_app(), base_url=_LOCAL)


def _patch_init(monkeypatch, fn):
    # Deterministic import — never depend on an earlier test having built the app.
    # Patch the module that DEFINES and CALLS _run_cos_init: the route resolves it
    # from its own globals, so patching the hub facade's re-export would miss.
    import web.routes._hub_init_routes as init_routes

    monkeypatch.setattr(init_routes, "_run_cos_init", fn)


class TestInitRouteValidation:
    def test_bad_name_rejected(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "Bad Name!", "parent_dir": str(hub_env)},
            )
        assert resp.status_code == 400
        assert resp.json()["error"]["category"] == "validation"

    def test_missing_parent_dir_rejected(self, hub_env):
        with _client() as client:
            resp = client.post("/api/hub/registry/init", json={"name": "proj", "parent_dir": "  "})
        assert resp.status_code == 400

    def test_parent_not_a_dir(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(hub_env / "nope")},
            )
        assert resp.status_code == 404

    def test_target_already_exists(self, hub_env):
        (hub_env / "proj").mkdir()
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(hub_env)},
            )
        assert resp.status_code == 409

    def test_refuses_meta_repo_parent(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(_REPO_ROOT)},
            )
        assert resp.status_code == 400
        assert "meta-repo" in resp.json()["error"]["message"]


class TestInitRouteRun:
    def test_happy_path_returns_slug(self, hub_env, monkeypatch):
        _patch_init(monkeypatch, lambda *a, **k: (True, {"slug": "proj"}, ""))
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(hub_env), "stack": "python"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["slug"] == "proj"

    def test_failed_init_cleans_up_partial_scaffold(self, hub_env, monkeypatch):
        # Simulate init creating a partial dir then failing — the route must rmtree it.
        def _fake(
            name,
            parent_dir,
            stacks,
            agent,
            preset="",
            description="",
            extra_skills=None,
            disabled_modules=None,
            timeout=180,
        ):
            (Path(parent_dir) / name).mkdir(parents=True, exist_ok=True)
            return (False, None, "boom")

        _patch_init(monkeypatch, _fake)
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "halfbaked", "parent_dir": str(hub_env)},
            )
        assert resp.status_code == 500
        assert not (hub_env / "halfbaked").exists()  # partial scaffold removed


class TestValidateInitEndpoint:
    def test_valid_request_with_preview_and_auto_name(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/validate-init",
                json={"parent_dir": str(hub_env), "stacks": ["nextjs", "fastapi"]},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["valid"] is True
        assert data["auto_named"] is True  # "don't know yet" path
        assert data["name"].startswith("proj-")
        assert data["templates"] == ["nextjs", "fastapi"]
        assert "backend" in data["swimlanes"] and "frontend" in data["swimlanes"]

    def test_preset_expands_to_templates(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/validate-init",
                json={"name": "p1", "parent_dir": str(hub_env), "preset": "nextjs-fastapi"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["templates"] == ["nextjs", "fastapi"]

    def test_unknown_stack_and_agent_rejected(self, hub_env):
        with _client() as client:
            bad_stack = client.post(
                "/api/hub/registry/validate-init",
                json={"name": "p1", "parent_dir": str(hub_env), "stacks": ["no-such"]},
            )
            bad_agent = client.post(
                "/api/hub/registry/validate-init",
                json={"name": "p1", "parent_dir": str(hub_env), "agent": "no-such"},
            )
        assert bad_stack.status_code == 400
        assert "no-such" in bad_stack.json()["error"]["message"]
        assert bad_agent.status_code == 400
        assert "available" in bad_agent.json()["error"]["message"]

    def test_dry_run_writes_nothing(self, hub_env):
        before = sorted(p.name for p in hub_env.iterdir())
        with _client() as client:
            client.post(
                "/api/hub/registry/validate-init",
                json={"parent_dir": str(hub_env), "stacks": ["python"]},
            )
        assert sorted(p.name for p in hub_env.iterdir()) == before


class TestInitJobRoutes:
    def _start_fake_job(self, tmp_path, script="print('Initializing coding-os in /x')"):
        from web import init_jobs

        return init_jobs.start_job(
            [sys.executable, "-u", "-c", script], tmp_path / "jobproj", str(tmp_path), lambda _: {}
        )

    def test_background_create_returns_job_id(self, hub_env, monkeypatch):
        from web import init_jobs

        captured: dict = {}

        def _fake_start(cmd, target, cwd, parse):
            captured["cmd"] = cmd
            job = init_jobs.InitJob(job_id="job-test123456", target=target)
            job.status = "running"
            init_jobs._JOBS[job.job_id] = job
            return job

        monkeypatch.setattr(init_jobs, "start_job", _fake_start)
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={
                    "name": "bgproj",
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "background": True,
                },
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["job_id"] == "job-test123456"
        assert "--template" in captured["cmd"] and "python" in captured["cmd"]

    def test_job_snapshot_and_unknown_404(self, hub_env, tmp_path):
        import time

        job = self._start_fake_job(tmp_path)
        deadline = time.time() + 10
        while job.snapshot()["status"] == "running" and time.time() < deadline:
            time.sleep(0.05)
        with _client() as client:
            ok_resp = client.get(f"/api/hub/init-jobs/{job.job_id}")
            missing = client.get("/api/hub/init-jobs/job-ghost")
        assert ok_resp.status_code == 200
        assert ok_resp.json()["data"]["status"] == "succeeded"
        assert missing.status_code == 404

    def test_job_events_stream_replays_to_terminal(self, hub_env, tmp_path):
        import time

        job = self._start_fake_job(tmp_path, script="print('hello-log-line')")
        deadline = time.time() + 10
        while job.snapshot()["status"] == "running" and time.time() < deadline:
            time.sleep(0.05)
        with _client() as client:
            resp = client.get(f"/api/hub/init-jobs/{job.job_id}/events")
        assert resp.status_code == 200
        body = resp.text
        assert "event: log" in body and "hello-log-line" in body
        assert "event: succeeded" in body  # terminal frame closes the stream

    def test_cancel_route_unknown_404(self, hub_env):
        with _client() as client:
            resp = client.post("/api/hub/init-jobs/job-ghost/cancel")
        assert resp.status_code == 404

    def test_metrics_exposes_funnel_counters(self, hub_env):
        with _client() as client:
            resp = client.get("/metrics")
        assert resp.status_code == 200
        assert 'cos_init_jobs_total{status="started"}' in resp.text


class TestSecurityHardening:
    def test_traversal_names_rejected_with_no_fs_effect(self, hub_env):
        before = sorted(p.name for p in hub_env.iterdir())
        with _client() as client:
            for bad in ("../evil", "a/b", "..", ".hidden", "a\\b"):
                resp = client.post(
                    "/api/hub/registry/init",
                    json={"name": bad, "parent_dir": str(hub_env)},
                )
                assert resp.status_code == 400, f"{bad!r} → {resp.status_code}"
        assert sorted(p.name for p in hub_env.iterdir()) == before

    def test_rename_traversal_slug_rejected(self, hub_env):
        with _client() as client:
            resp = client.patch("/api/hub/registry/whatever", json={"new_slug": "../etc"})
        assert resp.status_code == 400

    def test_unknown_extra_skill_rejected_before_argv(self, hub_env, monkeypatch):
        called = []
        _patch_init(monkeypatch, lambda *a, **k: called.append(1) or (True, {}, ""))
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={
                    "name": "p1",
                    "parent_dir": str(hub_env),
                    "extra_skills": ["redis", "$(rm -rf /)"],
                },
            )
        assert resp.status_code == 400
        assert "unknown skill" in resp.json()["error"]["message"]
        assert called == []  # subprocess never spawned

    def test_token_mode_blocks_unauthenticated_mutations(self, hub_env, monkeypatch):
        monkeypatch.setenv("COS_HUB_TOKEN", "sekret-token")
        with _client() as client:
            no_auth = client.post(
                "/api/hub/registry/init", json={"name": "p1", "parent_dir": str(hub_env)}
            )
            wrong = client.post(
                "/api/hub/registry/init",
                json={"name": "p1", "parent_dir": str(hub_env)},
                headers={"Authorization": "Bearer wrong"},
            )
            read_ok = client.get("/api/hub/stacks")
        assert no_auth.status_code == 401
        assert wrong.status_code == 401
        assert read_ok.status_code == 200  # reads stay open

    def test_token_mode_allows_bearer_holder(self, hub_env, monkeypatch):
        monkeypatch.setenv("COS_HUB_TOKEN", "sekret-token")
        _patch_init(monkeypatch, lambda *a, **k: (True, {"slug": "p1"}, ""))
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "p1", "parent_dir": str(hub_env), "stacks": ["python"]},
                headers={"Authorization": "Bearer sekret-token"},
            )
        assert resp.status_code == 200, resp.text
