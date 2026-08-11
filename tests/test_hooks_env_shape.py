"""
Tests for core/hooks/ — parameterization, syntax, and COS_STATE_DIR support.

Covers:
  - All hooks pass bash -n syntax check
  - cos-env.sh sets correct defaults
  - cos-env.sh respects COS_STATE_DIR override
  - write-state.sh and check-state.sh round-trip
  - Gate hooks respond to correct state values
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks"


def run_hook(
    hook_name: str,
    stdin: str = "",
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a hook script with optional stdin and environment overrides."""
    hook_path = HOOKS_DIR / hook_name
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(hook_path)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=10,
    )


REPO_SRC = HOOKS_DIR.parent.parent  # <repo>/src — for the canonical Python resolver


def _resolve_cos_var(
    var: str,
    cwd: str,
    env_overrides: dict[str, str] | None = None,
    strip: tuple[str, ...] = ("CLAUDE_PROJECT_DIR", "COS_PROJECT_ROOT", "COS_STATE_DIR"),
) -> str:
    """Source cos-env.sh from `cwd` and echo one exported var. The anchor env
    vars in `strip` are removed first so the upward marker-walk path runs."""
    env = {k: v for k, v in os.environ.items() if k not in strip}
    if env_overrides:
        env.update(env_overrides)
    script = 'source "{}"; echo "${}"'.format(HOOKS_DIR / "cos-env.sh", var)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=10,
    ).stdout.strip()


def _python_resolve_root(cwd: str) -> str:
    """Project root per the canonical Python resolver, run from `cwd`."""
    import sys

    code = (
        f"import sys; sys.path.insert(0, {str(REPO_SRC)!r}); "
        "from core.thinking_os._db_paths import _find_project_root_from_cwd; "
        "print(_find_project_root_from_cwd())"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    ).stdout.strip()


def _cos_clean_env(**overrides: str) -> dict[str, str]:
    """Inherited env minus every COS_* var — derived-value assertions must not
    depend on whatever the host shell or a sibling test exported."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("COS_")}
    env.update(overrides)
    return env


class TestHookSyntax:
    @pytest.fixture(params=sorted(HOOKS_DIR.glob("*.sh")), ids=lambda p: p.name)
    def hook_file(self, request: pytest.FixtureRequest) -> Path:
        return request.param

    def test_syntax_valid(self, hook_file: Path) -> None:
        result = subprocess.run(
            ["bash", "-n", str(hook_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"{hook_file.name} has syntax errors: {result.stderr}"


class TestStateRoundTrip:
    def test_write_and_read_state(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        state_file = state_dir / ".thinking_os-gate"

        # Write state
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "write-state.sh"), str(state_file), "CLEAR 1"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0
        assert state_file.exists()

        content = state_file.read_text().strip()
        # write-state.sh prepends session id; content should end with the value
        assert "CLEAR 1" in content

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        """write-state.sh creates intermediate parent dirs (per TASK-035 panel
        routing — writes to $COS_PANEL_DIR which may not exist yet on the
        first write of a fresh panel). Behaviour change from the historic
        "fail when parent missing" contract; covered by panel isolation tests."""
        state_file = tmp_path / "deep" / "nested" / "state"
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "write-state.sh"), str(state_file), "TEST"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert state_file.exists()
        assert "TEST" in state_file.read_text()


class TestHookScriptPaths:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    CORE_MODULE = REPO_ROOT / "src" / "core" / "thinking_os"

    def _must_exist(self, *candidates: Path) -> Path:
        for c in candidates:
            if c.exists():
                return c
        raise AssertionError(f"None of the candidate paths exist: {candidates}")

    def test_core_thinking_os_module_present(self) -> None:
        assert self.CORE_MODULE.is_dir(), (
            f"Expected {self.CORE_MODULE} — hooks use '../thinking_os/' after the bb27aac rename."
        )

    @pytest.mark.parametrize(
        "hook_name, target",
        [
            ("capture-observation.sh", "capture.py"),
            ("session-end.sh", "session_summary.py"),
            ("session-end.sh", "session_enrich.py"),
            ("session-context.sh", "session_summary.py"),
            ("session-context.sh", "session_startup.py"),
        ],
    )
    def test_hook_references_resolve_to_real_module(
        self,
        hook_name: str,
        target: str,
    ) -> None:
        """Ensure the target script every hook tries to execute actually
        resolves under core/thinking_os/. Guards the 2026-04 regression
        where scripts pointed at the pre-rename `thinking_os/` path."""
        hook_src = (HOOKS_DIR / hook_name).read_text()
        assert target in hook_src, f"{hook_name} no longer references {target}"
        assert (self.CORE_MODULE / target).exists(), (
            f"src/core/thinking_os/{target} missing — hook {hook_name} will silently no-op"
        )

    def test_capture_observation_path_resolves(self) -> None:
        """Direct assertion on the CAPTURE_PY line in capture-observation.sh."""
        src = (HOOKS_DIR / "capture-observation.sh").read_text()
        assert "../thinking_os/capture.py" in src, (
            "capture-observation.sh must reference ../thinking_os/capture.py "
            "(underscore), not the pre-rename hyphen path."
        )

    def test_auto_reindex_docs_sys_path(self) -> None:
        """auto-reindex-docs.sh embeds a sys.path.insert with the brain dir."""
        src = (HOOKS_DIR / "auto-reindex-docs.sh").read_text()
        assert "/thinking_os'" in src, (
            "auto-reindex-docs.sh sys.path.insert must use thinking_os/ (underscore)."
        )
