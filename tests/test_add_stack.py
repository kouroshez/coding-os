"""Tests for `cos add-stack`.

Uses real `cos init` fixtures (via subprocess in a temp dir) because
add-stack's value is in the end-to-end behavior — applying stack files,
diff-safe AGENTS.md regeneration, config updates, idempotency.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

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
    result = _run_cli([
        "init",
        "--agent", "claude",
        "--project-dir", str(target.parent),
        "--name", target.name,
        "--no-git",
        "--today", FROZEN_DATE,
    ])
    assert result.returncode == 0, f"init failed: {result.stderr}"


def _init_with_stack(target: Path, stack: str) -> None:
    result = _run_cli([
        "init",
        "--agent", "claude",
        "--project-dir", str(target.parent),
        "--name", target.name,
        "--template", stack,
        "--no-git",
        "--today", FROZEN_DATE,
    ])
    assert result.returncode == 0, f"init failed: {result.stderr}"


# ---------- happy path ----------

def test_add_stack_django_to_base_project(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)

    result = _run_cli(["add-stack", "django", "-d", str(project)])
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Added stack 'django'" in result.stdout

    config = yaml.safe_load((project / ".coding-os.yaml").read_text())
    assert "django" in config["templates"]
    assert len(config.get("stack_history", [])) == 1
    assert config["stack_history"][0]["stack_id"] == "django"


def test_add_stack_regenerates_agents_md_with_backup(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    old_agents = (project / "AGENTS.md").read_text()

    _run_cli(["add-stack", "django", "-d", str(project)])
    new_agents = (project / "AGENTS.md").read_text()
    assert new_agents != old_agents
    # Stack content should appear in the regenerated file
    assert "Django" in new_agents or "backend" in new_agents.lower()

    backups = list((project / ".coding-os" / "backups").glob("AGENTS.md.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == old_agents


def test_add_stack_no_regen_flag_leaves_agents_md_intact(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    old_agents = (project / "AGENTS.md").read_text()

    result = _run_cli([
        "add-stack", "django", "-d", str(project), "--no-regen-agents-md",
    ])
    assert result.returncode == 0
    assert (project / "AGENTS.md").read_text() == old_agents
    # No backup created
    backups_dir = project / ".coding-os" / "backups"
    assert not backups_dir.exists() or not any(backups_dir.iterdir())


# ---------- idempotency ----------

def test_add_stack_already_installed_is_noop(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_with_stack(project, "django")

    result = _run_cli(["add-stack", "django", "-d", str(project)])
    assert result.returncode == 0
    assert "already installed" in result.stdout.lower()


def test_add_stack_twice_is_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)

    r1 = _run_cli(["add-stack", "django", "-d", str(project)])
    assert r1.returncode == 0

    r2 = _run_cli(["add-stack", "django", "-d", str(project)])
    assert r2.returncode == 0
    assert "already installed" in r2.stdout.lower()

    config = yaml.safe_load((project / ".coding-os.yaml").read_text())
    # Still exactly once in templates
    assert config["templates"].count("django") == 1
    # stack_history has exactly one entry
    assert len(config["stack_history"]) == 1


# ---------- multi-stack ----------

def test_add_multiple_stacks(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)

    _run_cli(["add-stack", "django", "-d", str(project)])
    r = _run_cli(["add-stack", "nextjs", "-d", str(project)])
    assert r.returncode == 0

    config = yaml.safe_load((project / ".coding-os.yaml").read_text())
    assert set(config["templates"]) == {"django", "nextjs"}
    assert len(config["stack_history"]) == 2

    agents = (project / "AGENTS.md").read_text()
    # Both stacks leave a mark
    assert "Django" in agents
    assert "Next.js" in agents


# ---------- errors ----------

def test_add_stack_unknown_errors(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    result = _run_cli(["add-stack", "ghoststack", "-d", str(project)])
    assert result.returncode != 0
    assert "not found" in result.stderr or "not found" in result.output


def test_add_stack_without_init_errors(tmp_path: Path) -> None:
    result = _run_cli(["add-stack", "django", "-d", str(tmp_path)])
    assert result.returncode != 0
    assert ".coding-os.yaml" in (result.stderr + result.stdout)


# ---------- JSON output ----------

def test_add_stack_json_output(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    result = _run_cli(
        ["add-stack", "django", "-d", str(project), "--format", "json"]
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["stack_id"] == "django"
    assert payload["already_installed"] is False
    assert "files_copied" in payload


# ---------- doctor integration ----------

# ---------- path-scoped rules ----------

def test_add_stack_copies_rules_to_claude_rules_dir(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])

    rule_file = project / ".claude" / "rules" / "django-backend.md"
    assert rule_file.exists(), "django rule should have been copied"
    content = rule_file.read_text()
    assert "globs:" in content
    assert "backend/**/*.py" in content


def test_add_stack_copies_rules_to_codex(tmp_path: Path) -> None:
    """Post-Phase G symmetry: Codex now has a rules dir mirroring Claude's,
    so add-stack copies stack-scoped rule files there too."""
    project = tmp_path / "proj"
    # Init a codex project
    result = _run_cli([
        "init", "--agent", "codex",
        "--project-dir", str(project.parent),
        "--name", project.name,
        "--no-git",
    ])
    assert result.returncode == 0
    _run_cli(["add-stack", "django", "-d", str(project)])

    codex_rules = project / ".codex" / "rules"
    assert codex_rules.is_dir(), "codex should have a rules dir (Phase G symmetry)"
    # The django stack ships a path-scoped backend rule — it should land
    # under .codex/rules/ just like .claude/rules/.
    django_rule = codex_rules / "django-backend.md"
    assert django_rule.exists(), (
        f"expected stack rule at {django_rule}; dir contains "
        f"{[p.name for p in codex_rules.iterdir()]}"
    )


def test_init_with_stack_copies_rules(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_with_stack(project, "django")
    rule_file = project / ".claude" / "rules" / "django-backend.md"
    assert rule_file.exists()


def test_doctor_passes_on_multi_stack_project(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _init_base(project)
    _run_cli(["add-stack", "django", "-d", str(project)])
    _run_cli(["add-stack", "nextjs", "-d", str(project)])

    result = _run_cli(["doctor", "-d", str(project)])
    assert result.returncode == 0, f"doctor failed: {result.stdout}\n{result.stderr}"
    # No line should begin with [FAIL] — the "0 FAIL" summary string is ok.
    fail_lines = [
        line for line in result.stdout.splitlines() if line.startswith("[FAIL]")
    ]
    assert not fail_lines, f"doctor reported failures: {fail_lines}"
