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

from web.server import create_app  # noqa: E402

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
    import web.routes.hub as hub_routes

    monkeypatch.setattr(hub_routes, "_run_cos_init", fn)


class TestStacksEndpoint:
    def test_lists_data_driven_stacks(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/stacks")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        ids = {s["id"] for s in data["stacks"]}
        assert data["count"] == len(data["stacks"]) > 0
        assert "_base" not in ids  # the base profile is not an installable stack
        assert "meta" in ids  # the meta stack ships in this repo
        for s in data["stacks"]:
            assert s["label"] and s["id"]


class TestPresetsEndpoint:
    def test_lists_data_driven_presets(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/presets")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] == len(data["presets"]) > 0
        by_id = {p["id"]: p for p in data["presets"]}
        assert by_id["nextjs-fastapi"]["stacks"] == ["nextjs", "fastapi"]
        for p in data["presets"]:
            assert p["label"] and p["id"] and p["stacks"]


class TestSkillCatalogEndpoints:
    def test_global_skill_catalog(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/skills")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] == len(data["skills"]) > 0
        assert {e["provenance"] for e in data["skills"]} >= {"core"}

    def test_stack_skill_groups(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/stacks/fastapi/skills")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["stack"] == "fastapi"
        assert set(data["groups"]) == {"required", "recommended", "optional"}
        assert data["groups"]["required"][0]["name"] == "python-fastapi"

    def test_unknown_stack_404(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/stacks/no-such/skills")
        assert resp.status_code == 404


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
        def _fake(name, parent_dir, stacks, agent, preset="", description="",
                  extra_skills=None, disabled_modules=None, timeout=180):
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


# ---------------------------------------------------------------------------
# Onboarding wizard backend — TASK-358
# ---------------------------------------------------------------------------


class TestAdaptersEndpoint:
    def test_lists_data_driven_adapters(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/adapters")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        ids = {a["id"] for a in data["adapters"]}
        assert "claude" in ids  # ships in this repo; no hardcoded single agent
        assert data["count"] == len(data["adapters"]) >= 2


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


class TestWizardCreateFlow:
    def test_multi_stack_create_forwards_description_and_extra_skills(self, hub_env, monkeypatch):
        """Wizard inputs ride the CLI flags (--summary/--skills) so wizard and
        hand-typed init produce identical projects (TASK-359 parity)."""
        calls: list[dict] = []

        def _fake(name, parent_dir, stacks, agents, preset="", description="",
                  extra_skills=None, disabled_modules=None, timeout=180):
            calls.append(
                {
                    "name": name,
                    "stacks": stacks,
                    "agents": agents,
                    "preset": preset,
                    "description": description,
                    "extra_skills": extra_skills,
                }
            )
            (Path(parent_dir) / name).mkdir(parents=True)
            return (True, {"slug": name}, "")

        _patch_init(monkeypatch, _fake)
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={
                    "parent_dir": str(hub_env),
                    "stacks": ["nextjs", "fastapi"],
                    "agent": "claude",
                    "description": "A two-paragraph product description.",
                    "extra_skills": ["redis", "docker"],
                },
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["auto_named"] is True and data["slug"].startswith("proj-")
        assert calls == [
            {
                "name": data["slug"],
                "stacks": ["nextjs", "fastapi"],
                "agents": ["claude"],
                "preset": "",
                "description": "A two-paragraph product description.",
                "extra_skills": ["redis", "docker"],
            }
        ]

    def test_multi_agent_create_installs_both_adapters(self, hub_env, monkeypatch):
        """A project may host several adapters: agents=[claude,codex] reaches
        the scaffolder as a list and echoes back in the response (TASK-419)."""
        calls: list[dict] = []

        def _fake(name, parent_dir, stacks, agents, preset="", description="",
                  extra_skills=None, disabled_modules=None, timeout=180):
            calls.append({"agents": agents})
            (Path(parent_dir) / name).mkdir(parents=True)
            return (True, {"slug": name}, "")

        _patch_init(monkeypatch, _fake)
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={
                    "name": "multi",
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "agents": ["claude", "codex"],
                },
            )
        assert resp.status_code == 200, resp.text
        assert calls == [{"agents": ["claude", "codex"]}]
        assert resp.json()["data"]["agents"] == ["claude", "codex"]

    def test_validate_init_echoes_resolved_agents_and_rejects_unknown(self, hub_env):
        """validate-init surfaces the resolved agent list for the live preview
        and rejects an unknown adapter in the list (TASK-419)."""
        with _client() as client:
            good = client.post(
                "/api/hub/registry/validate-init",
                json={"parent_dir": str(hub_env), "stacks": ["python"],
                      "agents": ["claude", "codex"]},
            )
            bad = client.post(
                "/api/hub/registry/validate-init",
                json={"parent_dir": str(hub_env), "stacks": ["python"],
                      "agents": ["claude", "no-such"]},
            )
        assert good.status_code == 200, good.text
        assert good.json()["data"]["agents"] == ["claude", "codex"]
        assert bad.status_code == 400
        assert "no-such" in bad.json()["error"]["message"]

    def test_preset_and_stacks_mutually_exclusive(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={
                    "name": "p2",
                    "parent_dir": str(hub_env),
                    "stacks": ["nextjs"],
                    "preset": "nextjs-fastapi",
                },
            )
        assert resp.status_code == 400
        assert "mutually exclusive" in resp.json()["error"]["message"]


class TestModuleToggles:
    def test_modules_catalog_lists_kernel_and_deps(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/modules")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        by_id = {m["id"]: m for m in data["modules"]}
        assert by_id["kernel"]["kernel"] is True
        assert "docs" in by_id["tasks"]["depends_on"]
        assert data["count"] == len(data["modules"]) >= 6

    def test_init_forwards_disabled_modules(self, hub_env, monkeypatch):
        captured: dict = {}

        def _fake(name, parent_dir, stacks, agents, preset="", description="",
                  extra_skills=None, disabled_modules=None, timeout=180):
            captured["disabled_modules"] = disabled_modules
            (Path(parent_dir) / name).mkdir(parents=True)
            return (True, {"slug": name}, "")

        _patch_init(monkeypatch, _fake)
        with _client() as client:
            resp = client.post("/api/hub/registry/init", json={
                "name": "modproj", "parent_dir": str(hub_env), "stacks": ["python"],
                "disabled_modules": ["graph", "memory"],
            })
        assert resp.status_code == 200, resp.text
        assert captured["disabled_modules"] == ["graph", "memory"]
        assert resp.json()["data"]["disabled_modules"] == ["graph", "memory"]

    def test_validate_init_rejects_unknown_and_kernel_modules(self, hub_env):
        with _client() as client:
            unknown = client.post("/api/hub/registry/validate-init", json={
                "parent_dir": str(hub_env), "stacks": ["python"], "disabled_modules": ["nope"]})
            kernel = client.post("/api/hub/registry/validate-init", json={
                "parent_dir": str(hub_env), "stacks": ["python"], "disabled_modules": ["kernel"]})
            good = client.post("/api/hub/registry/validate-init", json={
                "parent_dir": str(hub_env), "stacks": ["python"], "disabled_modules": ["graph"]})
        assert unknown.status_code == 400
        assert "unknown module" in unknown.json()["error"]["message"].lower()
        assert kernel.status_code == 400
        assert "kernel" in kernel.json()["error"]["message"].lower()
        assert good.status_code == 200
        assert good.json()["data"]["disabled_modules"] == ["graph"]


class TestRegistryRename:
    def test_temp_slug_renames_without_breaking_entry(self, hub_env):
        from cli.registry import add_project, load_registry

        proj = hub_env / "proj-abc123"
        (proj / ".coding-os").mkdir(parents=True)
        add_project(proj, slug="proj-abc123")
        with _client() as client:
            resp = client.patch(
                "/api/hub/registry/proj-abc123", json={"new_slug": "real-name"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["slug"] == "real-name"
        entries = {p.slug: p.path for p in load_registry().projects}
        assert entries["real-name"] == str(proj)  # path untouched

    def test_rename_unknown_404_and_duplicate_409(self, hub_env):
        from cli.registry import add_project

        for slug in ("one", "two"):
            d = hub_env / slug
            (d / ".coding-os").mkdir(parents=True)
            add_project(d, slug=slug)
        with _client() as client:
            missing = client.patch("/api/hub/registry/ghost", json={"new_slug": "x1"})
            dup = client.patch("/api/hub/registry/one", json={"new_slug": "two"})
        assert missing.status_code == 404
        assert dup.status_code == 409


# ---------------------------------------------------------------------------
# Job-based create + SSE — TASK-362
# ---------------------------------------------------------------------------


class TestInitJobRoutes:
    def _start_fake_job(self, tmp_path, script="print('Initializing coding-os in /x')"):
        from web import init_jobs

        return init_jobs.start_job(
            [sys.executable, "-u", "-c", script], tmp_path / "jobproj", str(tmp_path), lambda _: {}
        )

    def test_background_create_returns_job_id(self, hub_env, monkeypatch):
        import web.routes.hub as hub_routes
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


# ---------------------------------------------------------------------------
# Security hardening regressions — TASK-363 (hub-threat-model.md)
# ---------------------------------------------------------------------------


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
