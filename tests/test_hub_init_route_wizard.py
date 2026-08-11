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


class TestWizardCreateFlow:
    def test_multi_stack_create_forwards_description_and_extra_skills(self, hub_env, monkeypatch):
        """Wizard inputs ride the CLI flags (--summary/--skills) so wizard and
        hand-typed init produce identical projects (TASK-359 parity)."""
        calls: list[dict] = []

        def _fake(
            name,
            parent_dir,
            stacks,
            agents,
            preset="",
            description="",
            extra_skills=None,
            disabled_modules=None,
            timeout=180,
        ):
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

        def _fake(
            name,
            parent_dir,
            stacks,
            agents,
            preset="",
            description="",
            extra_skills=None,
            disabled_modules=None,
            timeout=180,
        ):
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
                json={
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "agents": ["claude", "codex"],
                },
            )
            bad = client.post(
                "/api/hub/registry/validate-init",
                json={
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "agents": ["claude", "no-such"],
                },
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

        def _fake(
            name,
            parent_dir,
            stacks,
            agents,
            preset="",
            description="",
            extra_skills=None,
            disabled_modules=None,
            timeout=180,
        ):
            captured["disabled_modules"] = disabled_modules
            (Path(parent_dir) / name).mkdir(parents=True)
            return (True, {"slug": name}, "")

        _patch_init(monkeypatch, _fake)
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={
                    "name": "modproj",
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "disabled_modules": ["graph", "memory"],
                },
            )
        assert resp.status_code == 200, resp.text
        assert captured["disabled_modules"] == ["graph", "memory"]
        assert resp.json()["data"]["disabled_modules"] == ["graph", "memory"]

    def test_validate_init_rejects_unknown_and_kernel_modules(self, hub_env):
        with _client() as client:
            unknown = client.post(
                "/api/hub/registry/validate-init",
                json={
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "disabled_modules": ["nope"],
                },
            )
            kernel = client.post(
                "/api/hub/registry/validate-init",
                json={
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "disabled_modules": ["kernel"],
                },
            )
            good = client.post(
                "/api/hub/registry/validate-init",
                json={
                    "parent_dir": str(hub_env),
                    "stacks": ["python"],
                    "disabled_modules": ["graph"],
                },
            )
        assert unknown.status_code == 400
        assert "unknown module" in unknown.json()["error"]["message"].lower()
        assert kernel.status_code == 400
        assert "kernel" in kernel.json()["error"]["message"].lower()
        assert good.status_code == 200
        assert good.json()["data"]["disabled_modules"] == ["graph"]

    def test_modules_catalog_hides_hidden_and_exposes_default_profile(self, hub_env):
        from cli.subsystems import load_subsystems

        hidden = {m.id for m in load_subsystems().values() if m.hidden}
        with _client() as client:
            data = client.get("/api/hub/modules").json()["data"]
        listed = {m["id"] for m in data["modules"]}
        assert listed.isdisjoint(hidden)
        assert data["default_profile"]
        # The Composer seeds its chips from this — every id must be togglable.
        assert set(data["default_disabled"]) <= listed

    def test_init_cmd_emits_enable_module_instead_of_profile_pin(self):
        from cli.subsystems import load_profiles, load_subsystems, resolve_profile
        from web.routes.hub import _build_cos_init_cmd

        # No explicit set → no module flags at all, so a bare API create
        # matches a bare `cos init` (both land on the registry default).
        bare = _build_cos_init_cmd("proj", "/tmp", ["python"], ["claude"])
        assert "--profile" not in bare
        assert "--enable-module" not in bare

        # With a set, init UNIONS profile + --disable-module, so every visible
        # module the chips kept ON that the default profile disables must ride
        # as --enable-module — no profile pin needed to stay authoritative.
        cmd = _build_cos_init_cmd(
            "proj", "/tmp", ["python"], ["claude"], disabled_modules=["graph"]
        )
        assert "--profile" not in cmd
        modules = load_subsystems()
        _, default_name = load_profiles()
        expected = sorted(
            m for m in resolve_profile(default_name) if m != "graph" and not modules[m].hidden
        )
        emitted = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "--enable-module"]
        assert sorted(emitted) == expected

    def test_parse_init_payload_reads_pretty_printed_summary(self):
        from web.routes.hub import _parse_init_payload

        stdout = [
            "Initializing coding-os in /tmp/proj",
            "  Applying template: python",
            "{",
            '  "status": "ok",',
            '  "slug": "proj",',
            '  "path": "/tmp/proj"',
            "}",
        ]
        assert _parse_init_payload(stdout)["slug"] == "proj"

    def test_suggest_roots_marks_meta_repo_unscaffoldable(self, hub_env, monkeypatch):
        monkeypatch.setenv("COS_PROJECT_ROOT", str(_REPO_ROOT))
        with _client() as client:
            data = client.get("/api/hub/suggest-roots").json()["data"]
        assert str(_REPO_ROOT) in data["suggestions"]
        assert str(_REPO_ROOT) not in data["scaffoldable"]
