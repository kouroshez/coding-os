"""Behavior tests for test-governor.sh + record-verify-auto.sh (TASK-329/330).

Spec: docs/engineering/test-governance.md. Each test drives the hook with a
synthetic PreToolUse/PostToolUse Bash payload and an isolated COS_STATE_DIR;
COS_PROJECT_ROOT points at the real repo so `verify_suites_cli match-command`
and `tree-state` resolve against the live verify-suites.yaml and git tree.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "src" / "core" / "hooks"
GOVERNOR = HOOKS / "test-governor.sh"
AUTO_RECORD = HOOKS / "record-verify-auto.sh"

BOARD_SUITE_CMD = (
    "uv run --extra rag --with aiohttp --with pytest-asyncio "
    "pytest src/core/board_os/tests/ -q"
)


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / ".coding-os"
    state.mkdir()
    return state


def _env(state_dir: Path, **extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COS_TEST_FORCE", "COS_FULL_SWEEP_OK", "COS_OVERRIDE_REASON"))
    }
    env["COS_STATE_DIR"] = str(state_dir)
    env["COS_PROJECT_ROOT"] = str(REPO_ROOT)
    env.update(extra)
    return env


def _run_hook(hook: Path, payload: dict, state_dir: Path, **extra_env: str):
    proc = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=60,
        env=_env(state_dir, **extra_env),
        cwd=REPO_ROOT,
    )
    return proc.returncode, proc.stderr.decode()


def _tree_state() -> dict:
    out = subprocess.run(
        ["uv", "run", "--quiet", "python", "-m", "core.board_os.verify_suites_cli", "tree-state"],
        capture_output=True,
        timeout=60,
        cwd=REPO_ROOT,
    ).stdout
    return json.loads(out)


def _write_fresh_pass(state_dir: Path, suite: str) -> None:
    tree = _tree_state()
    entry = {
        "status": "PASS",
        "ts": int(time.time()),
        "git_head": tree["git_head"],
        "dirty_digest": tree["dirty_digest"],
        "agent": "peer-agent",
        "session_tail": "feedc0de",
    }
    (state_dir / ".last-verify.json").write_text(json.dumps({suite: entry}), encoding="utf-8")


class TestFullSweepGate:
    def test_bare_pytest_tests_blocks(self, state_dir: Path) -> None:
        code, err = _run_hook(
            GOVERNOR, {"tool_input": {"command": "uv run pytest tests/ -q"}}, state_dir
        )
        assert code == 2
        assert "Rule 20" in err
        assert "COS_FULL_SWEEP_OK" in err

    def test_pathless_pytest_blocks(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR, {"tool_input": {"command": "uv run pytest -q"}}, state_dir
        )
        assert code == 2

    def test_override_with_reason_allows(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR,
            {"tool_input": {"command": "uv run pytest tests/ -q"}},
            state_dir,
            COS_FULL_SWEEP_OK="1",
            COS_OVERRIDE_REASON="pre-merge final gate before release",
        )
        assert code == 0

    def test_override_with_short_reason_blocks(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR,
            {"tool_input": {"command": "uv run pytest tests/ -q"}},
            state_dir,
            COS_FULL_SWEEP_OK="1",
            COS_OVERRIDE_REASON="short",
        )
        assert code == 2

    def test_collect_only_is_exempt(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR,
            {"tool_input": {"command": "uv run pytest tests/ --collect-only -q"}},
            state_dir,
        )
        assert code == 0

    def test_targeted_suite_is_not_a_sweep(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR, {"tool_input": {"command": BOARD_SUITE_CMD}}, state_dir
        )
        assert code == 0


class TestDedup:
    def test_fresh_pass_same_tree_blocks_rerun(self, state_dir: Path) -> None:
        _write_fresh_pass(state_dir, "test-board_os")
        code, err = _run_hook(
            GOVERNOR, {"tool_input": {"command": BOARD_SUITE_CMD}}, state_dir
        )
        assert code == 2
        assert "already green" in err
        assert "peer-agent" in err

    def test_force_overrides_dedup(self, state_dir: Path) -> None:
        _write_fresh_pass(state_dir, "test-board_os")
        code, _ = _run_hook(
            GOVERNOR,
            {"tool_input": {"command": BOARD_SUITE_CMD}},
            state_dir,
            COS_TEST_FORCE="1",
        )
        assert code == 0

    def test_stale_v1_entry_allows_run(self, state_dir: Path) -> None:
        entry = {"status": "PASS", "ts": int(time.time())}
        (state_dir / ".last-verify.json").write_text(
            json.dumps({"test-board_os": entry}), encoding="utf-8"
        )
        code, _ = _run_hook(
            GOVERNOR, {"tool_input": {"command": BOARD_SUITE_CMD}}, state_dir
        )
        assert code == 0


class TestRunLock:
    def test_lock_in_grace_window_blocks(self, state_dir: Path) -> None:
        lock = {
            "suite": "test-thinking_os",
            "agent": "codex",
            "session_tail": "deadbeef",
            "started_ts": int(time.time()),
        }
        (state_dir / ".test-run.lock").write_text(json.dumps(lock), encoding="utf-8")
        code, err = _run_hook(
            GOVERNOR, {"tool_input": {"command": BOARD_SUITE_CMD}}, state_dir
        )
        assert code == 2
        assert "codex" in err

    def test_expired_lock_is_overwritten(self, state_dir: Path) -> None:
        lock = {
            "suite": "test-thinking_os",
            "agent": "codex",
            "session_tail": "deadbeef",
            "started_ts": int(time.time()) - 4000,
        }
        (state_dir / ".test-run.lock").write_text(json.dumps(lock), encoding="utf-8")
        code, _ = _run_hook(
            GOVERNOR, {"tool_input": {"command": BOARD_SUITE_CMD}}, state_dir
        )
        assert code == 0
        new_lock = json.loads((state_dir / ".test-run.lock").read_text(encoding="utf-8"))
        assert new_lock["agent"] != "codex"

    def test_allowed_run_writes_lock(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR, {"tool_input": {"command": BOARD_SUITE_CMD}}, state_dir
        )
        assert code == 0
        lock = json.loads((state_dir / ".test-run.lock").read_text(encoding="utf-8"))
        assert lock["suite"] == "test-board_os"


class TestFailOpen:
    def test_non_pytest_command_passes_through(self, state_dir: Path) -> None:
        code, _ = _run_hook(
            GOVERNOR, {"tool_input": {"command": "git status"}}, state_dir
        )
        assert code == 0

    def test_garbage_payload_passes_through(self, state_dir: Path) -> None:
        proc = subprocess.run(
            ["bash", str(GOVERNOR)],
            input=b"not json at all",
            capture_output=True,
            timeout=60,
            env=_env(state_dir),
            cwd=REPO_ROOT,
        )
        assert proc.returncode == 0


class TestAutoRecord:
    def test_pass_recorded_with_commit_keys_and_lock_cleared(self, state_dir: Path) -> None:
        (state_dir / ".test-run.lock").write_text("{}", encoding="utf-8")
        payload = {
            "tool_input": {"command": BOARD_SUITE_CMD},
            "tool_response": {"exit_code": 0},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        entry = ledger["test-board_os"]
        assert entry["status"] == "PASS"
        assert len(entry["git_head"]) == 40
        assert entry["dirty_digest"]
        assert not (state_dir / ".test-run.lock").exists()

    def test_failure_recorded_as_fail(self, state_dir: Path) -> None:
        payload = {
            "tool_input": {"command": BOARD_SUITE_CMD},
            "tool_response": {"exit_code": 1},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        assert ledger["test-board_os"]["status"] == "FAIL"

    def test_non_suite_command_ignored(self, state_dir: Path) -> None:
        payload = {
            "tool_input": {"command": "echo hello"},
            "tool_response": {"exit_code": 0},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()
