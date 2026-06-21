"""Tests for `cos remove-stack` (the reverse of `cos add-stack`).

End-to-end against real `cos init` + `cos add-stack` sandboxes (subprocess in a
temp dir) because remove-stack's value is its reversal behaviour — dropping the
stack from templates, unlinking skills, recomposing configs, and regenerating
AGENTS.md. The comment-preserving config-edit helpers are unit-tested directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from cli.remove_stack import _append_stack_history_block, _rewrite_templates_block

REPO_ROOT = Path(__file__).resolve().parent.parent
FROZEN_DATE = "2026-01-01"


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=str(cwd or REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _init_base(target: Path) -> None:
    result = _run_cli(
        [
            "init",
            "--agent",
            "claude",
            "--project-dir",
            str(target.parent),
            "--name",
            target.name,
            "--no-git",
            "--today",
            FROZEN_DATE,
        ]
    )
    assert result.returncode == 0, f"init failed: {result.stderr}"


# ---------- pure unit tests for the comment-preserving config editors ----------


def test_rewrite_templates_block_indented_preserves_comments() -> None:
    raw = (
        "version: '1.0'\n\n# keep me\nagents:\n  - claude\n\n"
        "templates:\n  - meta\n  - django\n\nstate_dir: .coding-os\n"
    )
    out = _rewrite_templates_block(raw, "django")
    assert "- django" not in out
    assert "- meta" in out
    assert "# keep me" in out
    assert "- claude" in out  # other lists untouched


def test_rewrite_templates_block_flush_dump_style() -> None:
    raw = "templates:\n- meta\n- django\nstate_dir: .coding-os\n"
    out = _rewrite_templates_block(raw, "django")
    assert "- django" not in out
    assert "- meta" in out


def test_rewrite_templates_block_quoted_scalar() -> None:
    raw = 'templates:\n  - "django"\n  - meta\n'
    out = _rewrite_templates_block(raw, "django")
    assert "django" not in out
    assert "- meta" in out


def test_rewrite_templates_block_does_not_touch_other_keys() -> None:
    raw = "agents:\n  - django\ntemplates:\n  - meta\n  - django\n"
    out = _rewrite_templates_block(raw, "django")
    # The agents list keeps its django; only the templates list loses it.
    assert out.count("django") == 1
    assert "agents:\n  - django" in out


def test_append_stack_history_opens_block_when_absent() -> None:
    raw = "version: '1.0'\ntemplates:\n  - meta\n"
    out = _append_stack_history_block(raw, "django")
    data = yaml.safe_load(out)
    assert data["stack_history"][0]["stack_id"] == "django"
    assert "removed_at" in data["stack_history"][0]


def test_append_stack_history_appends_to_existing_block() -> None:
    raw = (
        "templates:\n  - meta\n"
        "stack_history:\n- stack_id: django\n  added_at: '2026-01-01T00:00:00'\n"
    )
    out = _append_stack_history_block(raw, "django")
    data = yaml.safe_load(out)
    assert len(data["stack_history"]) == 2
    assert data["stack_history"][0].get("added_at")
    assert data["stack_history"][1]["stack_id"] == "django"
    assert data["stack_history"][1].get("removed_at")


def test_append_stack_history_inserts_before_following_key() -> None:
    raw = (
        "templates:\n  - meta\n"
        "stack_history:\n- stack_id: go\n  added_at: '2026-01-01T00:00:00'\n"
        "state_dir: .coding-os\n"
    )
    out = _append_stack_history_block(raw, "go")
    data = yaml.safe_load(out)
    assert data["state_dir"] == ".coding-os"
    assert len(data["stack_history"]) == 2
    assert data["stack_history"][1].get("removed_at")


# ---------- fast unit test for scaffold-doc removal (DOC-5 / TASK-502) ----------


def test_remove_stack_docs_backs_up_and_deletes(tmp_path: Path) -> None:
    """_remove_stack_docs deletes the stack's scaffolded docs (backed up first),
    manifest-driven from the stack's own scaffold/docs tree."""
    from cli.remove_stack import (
        TEMPLATES_DIR,
        _remove_stack_docs,
        overlay_template_dirs,
    )
    from cli.stack_registry import load_stack_registry

    stacks = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    if "go" not in stacks:
        pytest.skip("go stack not in registry")

    project = tmp_path / "proj"
    scaffold_root = stacks["go"].source_dir / "scaffold"
    copied: list[Path] = []
    for src in (scaffold_root / "docs").rglob("*"):
        if src.is_file() and src.name != ".gitkeep":
            rel = src.relative_to(scaffold_root)
            dest = project / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("scaffolded + locally edited", encoding="utf-8")
            copied.append(rel)
    assert copied, "go stack ships at least one scaffold doc"

    removed = _remove_stack_docs("go", project, (), stacks)

    assert set(removed) == {str(r) for r in copied}
    for rel in copied:
        assert not (project / rel).exists(), f"{rel} should have been removed"
    backups = list((project / ".coding-os" / "backups").glob("*.bak"))
    assert len(backups) == len(copied), "each removed doc is backed up first"


# ---------- end-to-end CLI tests (scaffold sandboxes) ----------


@pytest.mark.slow
def test_remove_stack_drops_from_templates_and_unlinks_skills(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    assert _run_cli(["add-stack", "django", "-d", str(project)]).returncode == 0

    # The django skill is linked after add-stack.
    skill_link = project / ".claude" / "skills" / "python-django"
    assert skill_link.exists(), "add-stack should have linked python-django"

    result = _run_cli(["remove-stack", "django", "-d", str(project)])
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Removed stack 'django'" in result.stdout

    config = yaml.safe_load((project / ".coding-os.yaml").read_text())
    assert "django" not in (config.get("templates") or [])
    # Skill link gone.
    assert not skill_link.exists(), "remove-stack should have unlinked python-django"
    # stack_history records the removal.
    history = config.get("stack_history") or []
    assert any(h.get("stack_id") == "django" and h.get("removed_at") for h in history)


@pytest.mark.slow
def test_remove_stack_regenerates_agents_md_with_backup(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])
    with_django = (project / "AGENTS.md").read_text()
    assert "Django" in with_django

    result = _run_cli(["remove-stack", "django", "-d", str(project)])
    assert result.returncode == 0
    after = (project / "AGENTS.md").read_text()
    assert after != with_django
    assert "Django" not in after  # the stack section is gone

    backups = list((project / ".coding-os" / "backups").glob("AGENTS.md.*.bak"))
    assert backups, "an AGENTS.md backup should exist"
    assert any(b.read_text() == with_django for b in backups)


@pytest.mark.slow
def test_remove_stack_not_installed_is_noop(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    result = _run_cli(["remove-stack", "django", "-d", str(project)])
    assert result.returncode == 0
    assert "not installed" in result.stdout.lower()


@pytest.mark.slow
def test_remove_stack_preserves_config_comments(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])

    # Inject a hand-written comment into the consumer config.
    cfg = project / ".coding-os.yaml"
    text = cfg.read_text()
    text = text.replace("templates:", "# my stacks\ntemplates:", 1)
    cfg.write_text(text)

    assert _run_cli(["remove-stack", "django", "-d", str(project)]).returncode == 0

    out = cfg.read_text()
    assert "# my stacks" in out, "remove-stack must preserve user comments"
    assert "django" not in (yaml.safe_load(out).get("templates") or [])


@pytest.mark.slow
def test_remove_stack_keeps_shared_remaining_stack_skills(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])
    _run_cli(["add-stack", "nextjs", "-d", str(project)])

    result = _run_cli(["remove-stack", "django", "-d", str(project)])
    assert result.returncode == 0

    # django's skill is gone; nextjs's skill survives.
    assert not (project / ".claude" / "skills" / "python-django").exists()
    assert (project / ".claude" / "skills" / "nextjs-react").exists()

    config = yaml.safe_load((project / ".coding-os.yaml").read_text())
    assert config["templates"] == ["nextjs"]


@pytest.mark.slow
def test_remove_stack_removes_path_scoped_rules(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])
    rule_file = project / ".claude" / "rules" / "django-backend.md"
    assert rule_file.exists()

    _run_cli(["remove-stack", "django", "-d", str(project)])
    assert not rule_file.exists(), "remove-stack should drop the stack's path-scoped rules"


@pytest.mark.slow
def test_remove_stack_json_output(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])
    result = _run_cli(["remove-stack", "django", "-d", str(project), "--format", "json"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["stack_id"] == "django"
    assert payload["not_installed"] is False
    assert "unlinked_skills" in payload


@pytest.mark.slow
def test_remove_stack_no_regen_flag_leaves_agents_md_intact(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])
    before = (project / "AGENTS.md").read_text()

    result = _run_cli(["remove-stack", "django", "-d", str(project), "--no-regen-agents-md"])
    assert result.returncode == 0
    assert (project / "AGENTS.md").read_text() == before
    # Config still updated even when AGENTS.md is left intact.
    config = yaml.safe_load((project / ".coding-os.yaml").read_text())
    assert "django" not in (config.get("templates") or [])


@pytest.mark.slow
def test_remove_stack_without_init_errors(tmp_path: Path) -> None:
    result = _run_cli(["remove-stack", "django", "-d", str(tmp_path)])
    assert result.returncode != 0
    assert ".coding-os.yaml" in (result.stderr + result.stdout)
