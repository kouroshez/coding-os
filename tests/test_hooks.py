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

import json
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
    script = 'source "%s"; echo "$%s"' % (HOOKS_DIR / "cos-env.sh", var)
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
        "import sys; sys.path.insert(0, %r); "
        "from core.thinking_os.database import _find_project_root_from_cwd; "
        "print(_find_project_root_from_cwd())" % str(REPO_SRC)
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# Syntax validation — all hooks must pass bash -n
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# cos-env.sh — environment configuration
# ---------------------------------------------------------------------------


class TestCosEnv:
    def test_default_state_dir(self, tmp_path: Path) -> None:
        """Without COS_STATE_DIR, defaults to .coding-os."""
        script = 'source "{}"; echo "$COS_STATE_DIR"'.format(HOOKS_DIR / "cos-env.sh")
        base_env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_PROJECT_DIR",)
        }
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**base_env, "HOME": str(tmp_path)},
            timeout=10,
        )
        assert result.stdout.strip() == ".coding-os"

    def test_claude_project_dir_anchors_default_state_dir(self, tmp_path: Path) -> None:
        """Claude runs hooks with cwd != repo root; COS_STATE_DIR must still resolve."""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        script = 'source "{}"; echo "$COS_STATE_DIR"'.format(HOOKS_DIR / "cos-env.sh")
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(elsewhere),
            env={
                **{
                    k: v
                    for k, v in os.environ.items()
                    if k not in ("CLAUDE_PROJECT_DIR", "COS_STATE_DIR")
                },
                "HOME": str(tmp_path),
                "CLAUDE_PROJECT_DIR": str(fake_root),
            },
            timeout=10,
        )
        assert result.stdout.strip() == str(fake_root / ".coding-os")

    def test_marker_walk_anchors_root_from_subdir(self, tmp_path: Path) -> None:
        """The bug: with CLAUDE_PROJECT_DIR and COS_PROJECT_ROOT unset and cwd a
        nested subdir, cos-env.sh must walk up to the marked root, not lazily
        create a stray nested .coding-os/ at the subdir."""
        home = tmp_path / "home"
        root = home / "proj"
        (root / ".coding-os").mkdir(parents=True)
        (root / ".coding-os.yaml").write_text("version: '1.0'\n", encoding="utf-8")
        sub = root / "src" / "backend"
        sub.mkdir(parents=True)
        got = _resolve_cos_var("COS_STATE_DIR", str(sub), {"HOME": str(home)})
        assert got == os.path.realpath(str(root)) + "/.coding-os"

    def test_marker_walk_hard_stops_below_home(self, tmp_path: Path) -> None:
        """The walk must never bind $HOME/.coding-os (the global hub): a subdir
        under $HOME with no project markers falls back to the relative default."""
        home = tmp_path / "home"
        (home / ".coding-os").mkdir(parents=True)  # global-hub simulation
        sub = home / "randomproj" / "x"
        sub.mkdir(parents=True)
        got = _resolve_cos_var("COS_STATE_DIR", str(sub), {"HOME": str(home)})
        assert got == ".coding-os"

    def test_marker_walk_skips_stray_nested_state_dir(self, tmp_path: Path) -> None:
        """A stray nested .coding-os/ (no co-located marker) from a pre-fix run
        is skipped in favor of the marked root above it."""
        home = tmp_path / "home"
        root = home / "proj"
        (root / ".coding-os").mkdir(parents=True)
        (root / ".coding-os.yaml").write_text("version: '1.0'\n", encoding="utf-8")
        sub = root / "src" / "backend"
        (sub / ".coding-os").mkdir(parents=True)  # stray, no co-located marker
        got = _resolve_cos_var("COS_STATE_DIR", str(sub), {"HOME": str(home)})
        assert got == os.path.realpath(str(root)) + "/.coding-os"

    def test_cos_project_root_escape_hatch(self, tmp_path: Path) -> None:
        """COS_PROJECT_ROOT explicitly anchors the state dir when set, even from
        an unrelated cwd."""
        custom = tmp_path / "customroot"
        custom.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        got = _resolve_cos_var(
            "COS_STATE_DIR",
            str(elsewhere),
            {"COS_PROJECT_ROOT": str(custom), "HOME": str(tmp_path)},
        )
        assert got == str(custom / ".coding-os")

    def test_root_resolution_parity_with_database(self, tmp_path: Path) -> None:
        """cos-env.sh's walk must stay identical to the canonical Python resolver
        database.py::_find_project_root_from_cwd — same marker set AND same root
        for representative trees — so the two implementations cannot drift. (The
        shell's extra $HOME hard-stop is asserted separately; Python's equivalent
        is TASK-498, so parity fixtures keep the marked root strictly below $HOME
        where both already agree.)"""
        import re

        # (a) marker-set identity between the two implementations.
        db_src = (HOOKS_DIR.parent / "thinking_os" / "database.py").read_text(encoding="utf-8")
        m = re.search(r"_ROOT_MARKERS\s*=\s*\((.*?)\)", db_src, re.DOTALL)
        assert m, "could not find _ROOT_MARKERS in database.py"
        db_markers = set(re.findall(r"""["']([^"']+)["']""", m.group(1)))
        env_src = (HOOKS_DIR / "cos-env.sh").read_text(encoding="utf-8")
        fm = re.search(r"for marker in ([^\n;]+); do", env_src)
        assert fm, "could not find the marker loop in cos-env.sh"
        shell_markers = set(fm.group(1).split())
        assert shell_markers == db_markers, (
            f"marker drift: shell={sorted(shell_markers)} db={sorted(db_markers)}"
        )

        # (b) behavioral parity over representative trees.
        home = tmp_path / "home"
        a_root = home / "a"  # marked by .coding-os.yaml
        (a_root / ".coding-os").mkdir(parents=True)
        (a_root / ".coding-os.yaml").write_text("v\n", encoding="utf-8")
        a_sub = a_root / "src" / "backend"
        a_sub.mkdir(parents=True)
        b_root = home / "b"  # stray nested .coding-os/ below a marked root
        (b_root / ".coding-os").mkdir(parents=True)
        (b_root / ".coding-os.yaml").write_text("v\n", encoding="utf-8")
        b_sub = b_root / "src" / "x"
        (b_sub / ".coding-os").mkdir(parents=True)
        c_root = home / "c"  # marked by .git only (no yaml)
        (c_root / ".coding-os").mkdir(parents=True)
        (c_root / ".git").mkdir()
        c_sub = c_root / "pkg"
        c_sub.mkdir()

        for sub, expected in ((a_sub, a_root), (b_sub, b_root), (c_sub, c_root)):
            shell_root = os.path.dirname(
                _resolve_cos_var("COS_STATE_DIR", str(sub), {"HOME": str(home)})
            )
            py_root = _python_resolve_root(str(sub))
            assert (
                os.path.realpath(shell_root)
                == os.path.realpath(py_root)
                == os.path.realpath(str(expected))
            ), f"parity mismatch at {sub}: shell={shell_root} py={py_root} expected={expected}"

    def test_agent_marker_file_fallback_without_runtime_env(self, tmp_path: Path) -> None:
        """.coding-os/.agent is fallback when no runtime-specific env exists."""
        st = tmp_path / "state"
        st.mkdir()
        (st / ".agent").write_text("codex\n", encoding="utf-8")
        script_ag = 'source "{}"; echo "$COS_AGENT"'.format(HOOKS_DIR / "cos-env.sh")
        # Every env var that cos-env.sh treats as an authoritative runtime
        # signal must be stripped so we actually exercise the .agent file
        # fallback path — otherwise the outer pytest process (which has
        # CLAUDE_CODE_ENTRYPOINT set by the IDE) short-circuits detection.
        blocked_keys = {
            "COS_STATE_DIR",
            "COS_AGENT",
            "CODEX_SESSION_ID",
            "CODEX_AGENT_DIR",
            "CODEX_HOME",
            "CLAUDECODE",
            "CLAUDE_CODE_SSE_PORT",
            "CLAUDE_CODE_ENTRYPOINT",
            "CLAUDE_AGENT_SDK_VERSION",
            "CLAUDE_PROJECT_DIR",
        }
        result = subprocess.run(
            ["bash", "-c", script_ag],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={
                **{k: v for k, v in os.environ.items() if k not in blocked_keys},
                "HOME": str(tmp_path),
                "COS_STATE_DIR": str(st),
            },
            timeout=10,
        )
        assert result.stdout.strip() == "codex"

    def test_custom_state_dir(self, tmp_path: Path) -> None:
        """COS_STATE_DIR env var is respected."""
        script = 'source "{}"; echo "$COS_STATE_DIR"'.format(HOOKS_DIR / "cos-env.sh")
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "COS_STATE_DIR": ".my-custom-dir"},
            timeout=10,
        )
        assert result.stdout.strip() == ".my-custom-dir"

    def test_session_file_follows_state_dir(self, tmp_path: Path) -> None:
        """COS_SESSION_FILE lives inside the PANEL-private subdir (per TASK-035)
        so two panels of the same agent never share one file. The path shape is
        $COS_STATE_DIR/<agent>/panels/<panel-id>/session-id."""
        script = 'source "{}"; echo "$COS_SESSION_FILE"'.format(HOOKS_DIR / "cos-env.sh")
        # Pin COS_AGENT + COS_PANEL_ID so the path is deterministic regardless
        # of which Claude/Codex env vars happen to be set in the pytest shell.
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={
                **os.environ,
                "COS_STATE_DIR": ".custom",
                "COS_AGENT": "claude",
                "COS_PANEL_ID": "test-panel",
            },
            timeout=10,
        )
        assert result.stdout.strip() == ".custom/claude/panels/test-panel/session-id"

    def test_agent_dir_is_agent_scoped(self, tmp_path: Path) -> None:
        """COS_AGENT_DIR separates claude/ and codex/ state so concurrent
        agents on the same project cannot overwrite each other's markers."""
        script = 'source "{}"; echo "$COS_AGENT_DIR"'.format(HOOKS_DIR / "cos-env.sh")
        result_claude = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "COS_STATE_DIR": ".custom", "COS_AGENT": "claude"},
            timeout=10,
        )
        result_codex = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "COS_STATE_DIR": ".custom", "COS_AGENT": "codex"},
            timeout=10,
        )
        assert result_claude.stdout.strip() == ".custom/claude"
        assert result_codex.stdout.strip() == ".custom/codex"

    def test_db_path_follows_state_dir(self, tmp_path: Path) -> None:
        """COS_DB_PATH is derived from COS_STATE_DIR."""
        script = 'source "{}"; echo "$COS_DB_PATH"'.format(HOOKS_DIR / "cos-env.sh")
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "COS_STATE_DIR": ".custom"},
            timeout=10,
        )
        assert result.stdout.strip() == ".custom/coding-os.db"

    def test_db_path_override(self, tmp_path: Path) -> None:
        """COS_DB_PATH env var overrides the state-dir-derived default."""
        script = 'source "{}"; echo "$COS_DB_PATH"'.format(HOOKS_DIR / "cos-env.sh")
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "COS_DB_PATH": "/tmp/custom.db"},
            timeout=10,
        )
        assert result.stdout.strip() == "/tmp/custom.db"


# ---------------------------------------------------------------------------
# write-state.sh + check-state.sh round-trip
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Gate hooks — thinking_os-gate.sh parameterization
# ---------------------------------------------------------------------------


class TestThinkingOsGate:
    @pytest.fixture
    def gate_env(self, tmp_path: Path) -> tuple[Path, dict[str, str]]:
        """Set up a temp project with session + panel-scoped state dir
        (TASK-035: cognitive state lives at $COS_PANEL_DIR, not $COS_AGENT_DIR)."""
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        agent_dir = state_dir / "claude"
        agent_dir.mkdir()
        panel_id = "test-gate-panel"
        panel_dir = agent_dir / "panels" / panel_id
        panel_dir.mkdir(parents=True)
        session_id = "ses-claude-20260405-120000-ABCD"
        session_file = panel_dir / "session-id"
        session_file.write_text(session_id)
        env = {
            **os.environ,
            "COS_STATE_DIR": str(state_dir),
            "COS_AGENT_DIR": str(agent_dir),
            "COS_PANEL_ID": panel_id,
            "COS_PANEL_DIR": str(panel_dir),
            "COS_SESSION_FILE": str(session_file),
            "COS_AGENT": "claude",
        }
        return tmp_path, env

    def _write_gate(self, state_dir: Path, session_id: str, value: str) -> None:
        # Gate is per-panel. Use the same panel-id as gate_env.
        gate_file = state_dir / "claude" / "panels" / "test-gate-panel" / ".thinking_os-gate"
        gate_file.write_text(f"{session_id} {value}")

    def test_blocks_py_without_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "app/main.py", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 2

    def test_allows_py_with_valid_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        state_dir = Path(env["COS_STATE_DIR"])
        session_id = Path(env["COS_SESSION_FILE"]).read_text().strip()
        self._write_gate(state_dir, session_id, "CLEAR 1")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "app/main.py", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0

    def test_allows_md_without_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "docs/readme.md", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0

    def test_allows_test_file_without_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "tests/test_main.py",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Safety hooks — block-secrets.sh, block-dangerous-commands.sh
# ---------------------------------------------------------------------------


class TestBlockSecrets:
    def test_blocks_env_file(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git add backend/.env"},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_env_example(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git add .env.example"},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0

    def test_blocks_private_key_in_code(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "app/config.py",
                    "new_string": "-----BEGIN RSA PRIVATE KEY-----",
                },
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_secret_patterns_in_docs(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/security.md",
                    "new_string": "sk_live_example",
                },
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0

    def test_blocks_no_verify_flag(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit --no-verify -m "x"'},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_no_verify_inside_commit_message(self) -> None:
        # The flag named inside the -m message must NOT trip the flag block.
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit -m "docs: --no-verify is blocked now"'},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0


class TestBlockDangerousCommands:
    def test_blocks_force_push_main(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 2

    def test_blocks_rm_rf(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf backend"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_normal_git_push(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git push origin feature-branch"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 0

    def test_allows_normal_commands(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 0


class TestBlockProtectedFilesGovernanceEscape:
    """Regression tests for the task-name-based escape hatch in
    block-protected-files.sh.

    The hook must:
      - Block CLAUDE.md / AGENTS.md / core/rules edits when the active
        task has a generic name like 'feature-auth'.
      - Allow the same edits when the active task name matches governance
        patterns (docs-update, governance, claude-md-update, ...).

    This lets legitimate docs maintenance work proceed while keeping the
    safety net in place for accidental side-effect edits.
    """

    def _make_task_state(self, tmp_path: Path, task_name: str) -> dict[str, str]:
        """Build an env that points the hook at a temp panel-scoped state dir
        with a pre-written session-scoped .task-current file. Matches the
        post-TASK-035 layout: shared root + claude/ + panels/<panel-id>/."""
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        agent_dir = state_dir / "claude"
        agent_dir.mkdir()
        panel_id = "test-protect-panel"
        panel_dir = agent_dir / "panels" / panel_id
        panel_dir.mkdir(parents=True)
        session_id = "ses-claude-20260407-120000-TEST"
        (panel_dir / "session-id").write_text(session_id)
        (panel_dir / ".task-current").write_text(f"{session_id} {task_name}")
        return {
            "COS_STATE_DIR": str(state_dir),
            "COS_AGENT_DIR": str(agent_dir),
            "COS_PANEL_ID": panel_id,
            "COS_PANEL_DIR": str(panel_dir),
            "COS_SESSION_FILE": str(panel_dir / "session-id"),
            "COS_AGENT": "claude",
        }

    def test_blocks_claude_md_with_unrelated_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "feature-auth-flow")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/CLAUDE.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2

    def test_allows_claude_md_with_docs_update_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "docs-update-phase-d")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/CLAUDE.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_allows_agents_md_with_governance_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "governance-refactor")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/AGENTS.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_blocks_core_rules_with_unrelated_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "feature-checkout")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/.claude/rules/memory.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2

    def test_allows_normal_file_edit_regardless_of_task(self, tmp_path: Path) -> None:
        """Non-governance files are always allowed — the task-name filter
        only gates governance files."""
        env = self._make_task_state(tmp_path, "feature-cart")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "backend/apps/cart/services.py",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_allows_agents_md_with_multiword_governance_marker(self, tmp_path: Path) -> None:
        """Regression (TASK-097): a multi-word marker whose governance keyword
        is NOT the last token must still be recognised. The old `${VALUE##* }`
        extraction kept only the last word ('align-docs') and false-blocked."""
        env = self._make_task_state(tmp_path, "docs-update TASK-096 align-docs")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/repo/AGENTS.md", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_blocks_multiword_nongovernance_marker(self, tmp_path: Path) -> None:
        """The wider match must NOT leak: a multi-word non-governance marker
        still blocks governance edits."""
        env = self._make_task_state(tmp_path, "implement TASK-100 feature-auth")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/repo/AGENTS.md", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Regression: hook scripts must reference the current thinking_os/ module
# directory, not the pre-rename thinking_os/ path. See bb27aac rename commit.
# ---------------------------------------------------------------------------


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
