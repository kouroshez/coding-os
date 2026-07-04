"""Guards for the read-only Configuration routes (/api/config/*).

Available stacks/skills come from the installed package registry (deterministic
regardless of cwd); installed/mcp come from the active project files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src", _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_stacks_lists_available_registry(client):
    r = client.get("/api/config/stacks")
    assert r.status_code == 200
    body = r.json()
    assert "available" in body and "installed" in body
    ids = {s["id"] for s in body["available"]}
    assert "meta" in ids  # the package always ships the meta stack
    for s in body["available"]:
        assert {"id", "label", "category", "primary_skill", "installed"} <= set(s)


def test_skills_lists_core_registry(client):
    r = client.get("/api/config/skills")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0
    names = {s["name"] for s in body["skills"]}
    assert "clean-code" in names  # a core skill that always exists
    for s in body["skills"]:
        assert {"name", "tier", "domain"} <= set(s)


def test_mcp_reports_servers_shape(client):
    r = client.get("/api/config/mcp")
    assert r.status_code == 200
    body = r.json()
    assert "servers" in body
    for s in body["servers"]:
        assert "name" in s and "command" in s and "managed" in s


def test_adapters_groups_models_by_adapter(client):
    r = client.get("/api/config/adapters")
    assert r.status_code == 200
    body = r.json()
    assert body["default_model"] == "claude-opus-4-8"
    adapters = {a["id"]: a for a in body["adapters"]}

    claude = adapters["claude"]
    assert claude["runtime"] == "in_process" and claude["available"] is True
    assert len(claude["models"]) == 4
    assert sum(1 for m in claude["models"] if m["default"]) == 1  # exactly one default

    for rid in ("codex",):  # declared, but no fabricated model IDs (P7)
        assert adapters[rid]["runtime"] == "roadmap"
        assert adapters[rid]["available"] is False
        assert adapters[rid]["models"] == []

    assert body["adapters"][0]["id"] == "claude"  # the runnable adapter leads
    for a in body["adapters"]:
        assert {"id", "label", "runtime", "available", "models", "mcp_config_paths", "installed"} <= set(a)
    # installed reflects .coding-os.yaml::agents — the meta-repo runs claude only.
    assert claude["installed"] is True
    assert adapters["codex"]["installed"] is False

    # MCP wiring target per adapter (deduped mcp_launch.config_paths) — the
    # Adapters tab shows this so the UI never guesses the wiring file.
    assert claude["mcp_config_paths"] == [".mcp.json"]
    assert adapters["codex"]["mcp_config_paths"] == [".codex/config.toml"]


def test_skills_expose_installed_stacks_and_stack_membership(client):
    # TASK-786: the Skills tab groups active skills by the installed stacks that
    # use them, so the producer emits installed_stacks + a per-skill `stacks`.
    r = client.get("/api/config/skills")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["installed_stacks"], list)
    assert any(s["id"] == "meta" for s in body["installed_stacks"])  # meta-repo installs meta
    for s in body["skills"]:
        assert isinstance(s["stacks"], list)


def test_mcp_catalog_lists_first_party_allowlist(client):
    r = client.get("/api/config/mcp/catalog")
    assert r.status_code == 200
    body = r.json()
    ids = {s["id"] for s in body["servers"]}
    assert {"fetch", "git", "playwright"} <= ids  # curated first-party set
    for s in body["servers"]:
        assert {"id", "name", "command", "args", "installed"} <= set(s)


def test_mutations_refuse_on_the_meta_repo(client):
    # The TestClient resolves the project to the coding-os meta-repo (cwd), whose
    # .coding-os.yaml is DNA — every install/add mutation must refuse (409).
    assert client.post("/api/config/stacks/angular").status_code == 409
    assert client.delete("/api/config/stacks/meta").status_code == 409
    assert client.post("/api/config/adapters/codex").status_code == 409
    assert client.post("/api/config/mcp", json={"id": "fetch"}).status_code == 409


def test_mcp_add_rejects_units_off_the_allowlist(client, monkeypatch):
    import web.routes.config as cfg  # the module the app actually serves

    monkeypatch.setattr(cfg, "_is_meta_repo", lambda root: False)  # bypass the meta guard
    r = client.post("/api/config/mcp", json={"id": "evil-server"})
    assert r.status_code == 400
    assert r.json()["error"]["category"] == "validation"


def test_adapter_remove_refuses_the_last_adapter(client, monkeypatch, tmp_path):
    import web.routes.config as cfg  # the module the app actually serves

    (tmp_path / ".coding-os.yaml").write_text("agents:\n  - claude\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "_is_meta_repo", lambda root: False)
    monkeypatch.setattr(cfg, "_project_root", lambda: tmp_path)
    r = client.delete("/api/config/adapters/claude")
    assert r.status_code == 409
    assert "at least one adapter" in r.json()["error"]["message"]


def test_mutations_reject_option_injecting_ids(client):
    # A leading-dash path param must be rejected before it reaches the CLI argv,
    # where click would parse it as an option (e.g. add-stack --help).
    assert client.post("/api/config/stacks/--help").status_code == 400
    assert client.post("/api/config/adapters/-d").status_code == 400


def test_parse_cos_json_handles_multiline_and_fallback():
    import web.routes.config as cfg

    # cos add-stack --format json emits json.dumps(indent=2) — multi-line.
    multiline = '{\n  "status": "ok",\n  "files_copied": 3\n}'
    assert cfg._parse_cos_json(multiline) == {"status": "ok", "files_copied": 3}
    # single-line emitter mixed with noise → last {-prefixed line.
    assert cfg._parse_cos_json('scaffolding…\n{"status": "noop"}')["status"] == "noop"
    assert cfg._parse_cos_json("") == {}
    assert cfg._parse_cos_json("not json at all") == {}
