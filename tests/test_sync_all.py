"""Tests for cli.sync_all — cos sync-all + cos sync-doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cli.sync_all import (  # noqa: E402
    _dangling,
    _iter_symlinks,
    sync_all_cmd,
    sync_doctor_cmd,
)


@pytest.fixture
def registry_env(tmp_path, monkeypatch):
    """Isolated registry + two synthetic projects."""
    reg = tmp_path / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(reg))

    def make_project(name: str, with_broken_link: bool = False) -> Path:
        p = tmp_path / name
        (p / ".coding-os").mkdir(parents=True)
        (p / ".coding-os.yaml").write_text("agents: []\ntemplates: []\n", encoding="utf-8")
        (p / ".claude" / "hooks").mkdir(parents=True)
        # A healthy symlink to a real file (any file works for the test).
        real = tmp_path / "good-target.sh"
        real.write_text("#!/usr/bin/env bash\nexit 0\n")
        (p / ".claude" / "hooks" / "ok.sh").symlink_to(real)
        if with_broken_link:
            dead_target = tmp_path / "vanished" / "cos-env.sh"
            (p / ".claude" / "hooks" / "cos-env.sh").symlink_to(dead_target)
        return p

    from cli.registry import add_project

    alive = make_project("alive")
    broken = make_project("with-broken", with_broken_link=True)
    add_project(alive)
    add_project(broken)
    return {"tmp": tmp_path, "alive": alive, "broken": broken, "registry": reg}


# ---------------------------------------------------------------------------
# _iter_symlinks / _dangling
# ---------------------------------------------------------------------------


def test_iter_symlinks_finds_agent_dir_links(registry_env):
    links = _iter_symlinks(registry_env["alive"])
    assert any(link.name == "ok.sh" for link in links)


def test_dangling_detects_broken_target(registry_env):
    broken = registry_env["broken"] / ".claude" / "hooks" / "cos-env.sh"
    assert _dangling(broken) is True
    healthy = registry_env["alive"] / ".claude" / "hooks" / "ok.sh"
    assert _dangling(healthy) is False


# ---------------------------------------------------------------------------
# cos sync-all
# ---------------------------------------------------------------------------


def test_sync_all_reports_every_project(registry_env):
    result = CliRunner().invoke(sync_all_cmd, ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "alive" in result.output
    assert "with-broken" in result.output
    assert "2 project(s) processed" in result.output


def test_sync_all_surfaces_dangling_links(registry_env):
    result = CliRunner().invoke(sync_all_cmd, ["--dry-run"])
    assert "1 dangling symlink(s)" in result.output
    assert "with-broken" in result.output


def test_sync_all_slug_filter(registry_env):
    result = CliRunner().invoke(sync_all_cmd, ["--dry-run", "--slug", "alive"])
    assert "alive" in result.output
    assert "with-broken" not in result.output
    assert "1 project(s) processed" in result.output


def test_sync_all_dry_run_does_not_touch_registry(registry_env):
    before = registry_env["registry"].read_text()
    CliRunner().invoke(sync_all_cmd, ["--dry-run"])
    after = registry_env["registry"].read_text()
    assert before == after


# ---------------------------------------------------------------------------
# cos sync-doctor
# ---------------------------------------------------------------------------


def test_sync_doctor_json_output(registry_env):
    result = CliRunner().invoke(sync_doctor_cmd, ["--format", "json"])
    # exit code = number of still-broken projects (1 = with-broken).
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    slugs = {r["slug"]: r for r in payload}
    assert slugs["alive"]["dangling"] == []
    assert len(slugs["with-broken"]["dangling"]) == 1


def test_sync_doctor_healthy_projects_exit_zero(registry_env):
    # Remove the broken link so the project is clean.
    broken_link = registry_env["broken"] / ".claude" / "hooks" / "cos-env.sh"
    broken_link.unlink()
    result = CliRunner().invoke(sync_doctor_cmd, ["--format", "json"])
    assert result.exit_code == 0, result.output


def test_sync_doctor_slug_filter(registry_env):
    result = CliRunner().invoke(sync_doctor_cmd, ["--format", "json", "--slug", "alive"])
    payload = json.loads(result.output)
    assert [r["slug"] for r in payload] == ["alive"]
    assert result.exit_code == 0


def test_sync_doctor_repair_flag_runs_without_agents(registry_env):
    """When .coding-os.yaml has agents=[], --repair can't rewire links;
    the command must surface that state without crashing and still
    exit with the broken count."""
    result = CliRunner().invoke(sync_doctor_cmd, ["--repair", "--format", "json"])
    # Still 1 broken — repair with empty agents list is a no-op by design.
    assert result.exit_code == 1
    payload = json.loads(result.output)
    broken = next(r for r in payload if r["slug"] == "with-broken")
    assert broken["repaired_attempted"] is False  # no agents to run install.sh


def test_sync_doctor_skips_stale_project(registry_env):
    """Registry entries whose path no longer has .coding-os/ must be
    skipped (SKIP line to stderr) and the JSON on stdout must still
    parse.  Click 8.3 keeps stdout + stderr separate via result.stdout /
    result.stderr (no mix_stderr kwarg any more)."""
    import shutil

    shutil.rmtree(registry_env["alive"] / ".coding-os")
    result = CliRunner().invoke(sync_doctor_cmd, ["--format", "json"])
    payload = json.loads(result.stdout)
    slugs = [r["slug"] for r in payload]
    assert "alive" not in slugs  # skipped
    assert "with-broken" in slugs
    assert "SKIP alive" in result.stderr
