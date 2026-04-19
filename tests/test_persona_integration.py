"""End-to-end persona integration tests.

These tests assert that a `cos init` project — the artifact a real user
hands to Claude Code — has every moving part wired correctly and that
hooks fire in their intended scenarios. Each test is a short persona
scenario rather than a unit test of a single hook, so a regression that
disconnects two components (e.g. settings.json references a hook that
got renamed) gets caught here before a real session hits it.

Personas exercised:
  A) Fresh-install user               — init minimal project, doctor 14/15 PASS
  B) Full-stack user                  — init claude+django+nextjs, all skills wired
  C) Go + Fiber user                  — init claude+go-fiber, new stack works e2e
  D) Codex+claude dual-agent user     — add-adapter after init
  E) Upgrade user (simulated)         — cos update reports no drift after fresh init
  F) Agent writing a task file        — enforce-template blocks, redirect works
  G) Agent editing code without skill — enforce-skill blocks
  H) Agent editing code without gate  — thinking-os-gate blocks
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cos_bin() -> str:
    """Resolve the cos binary — editable install or repo venv."""
    installed = shutil.which("cos")
    if installed:
        return installed
    venv = REPO_ROOT / ".venv" / "bin" / "cos"
    if venv.exists():
        return str(venv)
    pytest.skip("cos binary not found")


def _run_cos(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_cos_bin(), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=60,
    )


# ============================================================
# Persona A — Fresh-install minimal
# ============================================================


class TestPersonaFreshInstall:
    def test_minimal_init_produces_valid_project(self, tmp_path: Path) -> None:
        project = tmp_path / "minimal"
        r = _run_cos(
            "init", "--agent", "claude",
            "--name", "minimal",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        assert r.returncode == 0, r.stderr

        # Core scaffold files exist.
        assert (project / ".coding-os.yaml").exists()
        assert (project / ".mcp.json").exists()
        assert (project / "AGENTS.md").exists()
        assert (project / ".claude" / "settings.json").exists()

        # .mcp.json uses the portable wrapper form.
        mcp = json.loads((project / ".mcp.json").read_text())
        assert mcp["mcpServers"]["coding-os"]["command"] == "cos"
        assert mcp["mcpServers"]["coding-os"]["args"] == ["server-start"]

        # Doctor passes every core check except stack-specific ones.
        r = _run_cos("doctor", "-d", str(project))
        # Base-only project: C13 stack_skills_linked PASS (no stacks)
        assert "FAIL" not in r.stdout or r.stdout.count("FAIL") <= 1, r.stdout


# ============================================================
# Persona B — Full-stack Django + Next.js
# ============================================================


class TestPersonaFullStack:
    def test_django_nextjs_init_wires_all_skills(self, tmp_path: Path) -> None:
        project = tmp_path / "fullstack"
        r = _run_cos(
            "init", "--agent", "claude",
            "--template", "django", "--template", "nextjs",
            "--name", "fullstack",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        assert r.returncode == 0, r.stderr

        # All stack skills symlinked into .claude/skills/.
        skills_dir = project / ".claude" / "skills"
        expected_skills = {
            "thinking-os", "clean-code", "codebase-explorer", "worktree-orchestration",
            "python-django", "nextjs-react", "frontend-design",
        }
        actual_skills = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        missing = expected_skills - actual_skills
        assert not missing, f"missing skills: {missing}"

        # All expected hooks symlinked (Phase F set).
        hooks_dir = project / ".claude" / "hooks"
        critical_hooks = {
            "warn-mcp-down.sh", "check-capture-worked.sh",
            "enforce-doc-anchor.sh", "enforce-memory-check.sh",
            "block-migration-conflict.sh", "block-hardcoded-literals.sh",
            "block-uv-heredoc.sh", "enforce-template.sh",
            "regen-reminder.sh", "test-first-reminder.sh",
            "doc-sync-reminder.sh", "remind-learn-validate.sh",
        }
        actual_hooks = {p.name for p in hooks_dir.iterdir()}
        missing = critical_hooks - actual_hooks
        assert not missing, f"missing hooks: {missing}"

    def test_doctor_passes_on_fullstack(self, tmp_path: Path) -> None:
        project = tmp_path / "fullstack-doctor"
        _run_cos(
            "init", "--agent", "claude",
            "--template", "django", "--template", "nextjs",
            "--name", "fullstack-doctor",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        r = _run_cos("doctor", "-d", str(project))
        # Every check should PASS on a freshly-scaffolded project.
        assert r.returncode == 0, f"doctor FAIL:\n{r.stdout}"
        assert "C15" in r.stdout and "PASS" in r.stdout
        assert "C14" in r.stdout and "PASS" in r.stdout
        assert "C13" in r.stdout and "PASS" in r.stdout


# ============================================================
# Persona C — Go + Fiber (new stack validation)
# ============================================================


class TestPersonaGoFiber:
    def test_go_fiber_init_wires_skill_and_scaffold(self, tmp_path: Path) -> None:
        project = tmp_path / "gofiber-app"
        r = _run_cos(
            "init", "--agent", "claude",
            "--template", "go-fiber",
            "--name", "gofiber-app",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        assert r.returncode == 0, r.stderr

        # go-fiber skill present.
        skill = project / ".claude" / "skills" / "go-fiber" / "SKILL.md"
        assert skill.exists(), "go-fiber skill not symlinked"

        # Scaffold docs present.
        assert (project / "docs" / "engineering" / "fiber-rules.md").exists()
        assert (project / "docs" / "playbooks" / "fiber-service.md").exists()

        # Path-scoped rule copied.
        assert (project / ".claude" / "rules" / "go-fiber-backend.md").exists()

        # .coding-os.yaml lists go-fiber.
        import yaml as _yaml
        cfg = _yaml.safe_load((project / ".coding-os.yaml").read_text())
        assert "go-fiber" in cfg["templates"]

        # Verify commands populated.
        assert cfg["verify"].get("backend", "").startswith("cd backend && go vet")

    def test_go_fiber_doctor_passes(self, tmp_path: Path) -> None:
        project = tmp_path / "gofiber-doctor"
        _run_cos(
            "init", "--agent", "claude",
            "--template", "go-fiber",
            "--name", "gofiber-doctor",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        r = _run_cos("doctor", "-d", str(project))
        assert r.returncode == 0, f"go-fiber doctor FAIL:\n{r.stdout}"


# ============================================================
# Persona D — Dual-agent (Claude + Codex)
# ============================================================


class TestPersonaDualAgent:
    def test_add_codex_after_claude_init(self, tmp_path: Path) -> None:
        project = tmp_path / "dual"
        _run_cos(
            "init", "--agent", "claude",
            "--template", "django",
            "--name", "dual",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        r = _run_cos("add-adapter", "codex", "-d", str(project))
        assert r.returncode == 0, r.stderr
        assert (project / ".codex").is_dir()
        assert (project / ".codex" / "hooks.json").exists()

        # Both adapters share the same core hook sources.
        claude_hook = (project / ".claude/hooks/thinking-os-gate.sh").resolve()
        codex_hook = (project / ".codex/hooks/thinking-os-gate.sh").resolve()
        assert claude_hook == codex_hook


# ============================================================
# Persona E — Upgrade (cos update on freshly-init'd project)
# ============================================================


class TestPersonaUpgrade:
    def test_update_on_fresh_project_reports_no_changes(self, tmp_path: Path) -> None:
        project = tmp_path / "upgrade"
        _run_cos(
            "init", "--agent", "claude",
            "--template", "go-fiber",
            "--name", "upgrade",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        r = _run_cos("update", "--dry-run", "-d", str(project))
        assert r.returncode == 0, r.stderr
        # Freshly-init'd → update diff should be empty.
        assert "No changes" in r.stdout or "Already up to date" in r.stdout, r.stdout

    def test_update_repairs_missing_symlink(self, tmp_path: Path) -> None:
        project = tmp_path / "repair"
        _run_cos(
            "init", "--agent", "claude",
            "--template", "django",
            "--name", "repair",
            "-d", str(tmp_path),
            "--no-git", "--yes",
        )
        # Simulate a user accidentally deleting a hook.
        victim = project / ".claude" / "hooks" / "block-secrets.sh"
        assert victim.is_symlink()
        victim.unlink()

        r = _run_cos("update", "-d", str(project))
        assert r.returncode == 0, r.stderr
        assert victim.exists(), "update did not re-link deleted hook"
        assert victim.is_symlink()


# ============================================================
# Persona F — Agent tries to hand-write a task file
# ============================================================


class TestPersonaTemplateBlock:
    def test_new_task_file_blocked(self, tmp_path: Path) -> None:
        hook = REPO_ROOT / "core" / "hooks" / "enforce-template.sh"
        target = tmp_path / "docs" / "tasks" / "TASK-999-bogus.md"
        r = subprocess.run(
            ["bash", str(hook)],
            input=json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            }),
            capture_output=True, text=True, timeout=5,
        )
        assert r.returncode == 2
        assert "task-create" in r.stderr


# Personas G / H (enforce-skill / thinking-os-gate without project context)
# are covered by the per-hook unit tests in test_hooks.py. The integration
# tests above focus on project-level flows that unit tests can't express.
