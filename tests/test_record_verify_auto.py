"""Behavior tests for record-verify-auto.sh — the verify-ledger recorder.

Spec: docs/engineering/test-governance.md § record-verify-auto. Each test feeds
the hook a synthetic PostToolUse Bash payload with an isolated COS_STATE_DIR;
COS_PROJECT_ROOT points at the real repo so `match-command` and `tree-state`
resolve against the live verify-suites.yaml and git tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None, reason="hooks resolve match-command via uv run"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTO_RECORD = REPO_ROOT / "src" / "core" / "hooks" / "record-verify-auto.sh"

BOARD_SUITE_CMD = (
    "uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q"
)


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / ".coding-os"
    state.mkdir()
    return state


def _run_hook(hook: Path, payload: dict, state_dir: Path):
    env = dict(os.environ, COS_STATE_DIR=str(state_dir), COS_PROJECT_ROOT=str(REPO_ROOT))
    proc = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=60,
        env=env,
        cwd=REPO_ROOT,
    )
    return proc.returncode, proc.stderr.decode()


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

    def test_a_refused_cos_run_leaves_the_ledger_to_cos_run(self, state_dir: Path) -> None:
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_input": {"command": "cos run test-backend"},
            "error": "exit 2",
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()

    def test_failure_recorded_as_fail(self, state_dir: Path) -> None:
        payload = {
            "tool_input": {"command": BOARD_SUITE_CMD},
            "tool_response": {"exit_code": 1},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        assert ledger["test-board_os"]["status"] == "FAIL"

    def test_failure_event_records_fail_without_exit_code(self, state_dir: Path) -> None:
        # PostToolUseFailure may carry no exit_code — the event itself is the
        # failure signal; the `// 0` default must not record a phantom PASS.
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_input": {"command": BOARD_SUITE_CMD},
            "tool_response": {},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        assert ledger["test-board_os"]["status"] == "FAIL"

    def test_live_success_shape_records_pass_without_an_exit_code(self, state_dir: Path) -> None:
        """Captured from a real Claude Code run, not assumed (TASK-1034).

        Claude Code sends no `exit_code` for Bash. Success arrives as
        PostToolUse carrying a tool_response object; failure arrives as
        PostToolUseFailure with no tool_response and a top-level `error`. The
        event is the outcome, so this shape is a genuine pass.
        """
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": BOARD_SUITE_CMD},
            "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        assert ledger["test-board_os"]["status"] == "PASS"

    @pytest.mark.parametrize(
        "payload",
        [
            {
                "hook_event_name": "PostToolUse",
                "tool_input": {"command": BOARD_SUITE_CMD, "run_in_background": True},
                "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
            },
            {
                "hook_event_name": "PostToolUse",
                "tool_input": {"command": BOARD_SUITE_CMD},
                "tool_response": {"stdout": "", "interrupted": False, "backgroundTaskId": "b1"},
            },
        ],
    )
    def test_a_background_launch_records_nothing_and_keeps_the_lock(
        self, state_dir: Path, payload: dict
    ) -> None:
        """Claude Code fires PostToolUse as soon as a background run starts."""
        (state_dir / ".test-run.lock").write_text("{}", encoding="utf-8")
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()
        assert (state_dir / ".test-run.lock").exists()

    def test_unknown_outcome_records_nothing(self, state_dir: Path) -> None:
        """No exit_code, no tool_response, no failure event — so, no record.

        `.last-verify.json` is what `enforce-verify.sh` reads to let
        `cos task-done` through, and `// 0` used to turn "the runtime said
        nothing" into a green light.
        """
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": BOARD_SUITE_CMD},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()

    def test_a_post_tool_use_carrying_an_error_records_nothing(self, state_dir: Path) -> None:
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": BOARD_SUITE_CMD},
            "tool_response": {"stdout": "x"},
            "error": "tool errored",
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()

    @pytest.mark.parametrize(
        "command",
        [
            f"{BOARD_SUITE_CMD} 2>&1 | tail -4",
            f"{BOARD_SUITE_CMD}; echo done",
            f"{BOARD_SUITE_CMD} || true",
            f"{BOARD_SUITE_CMD} &",
            f"{BOARD_SUITE_CMD}\necho done",
        ],
    )
    def test_a_command_that_can_mask_the_suite_records_no_pass(
        self, state_dir: Path, command: str
    ) -> None:
        """The outcome is the whole command's — `make x | tail` exits 0 when make failed."""
        payload = {"tool_input": {"command": command}, "tool_response": {"exit_code": 0}}
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()

    def test_a_masking_command_still_records_its_failure(self, state_dir: Path) -> None:
        payload = {
            "tool_input": {"command": f"{BOARD_SUITE_CMD} 2>&1 | tail -4"},
            "tool_response": {"exit_code": 1},
        }
        _run_hook(AUTO_RECORD, payload, state_dir)
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        assert ledger["test-board_os"]["status"] == "FAIL"

    def test_an_and_chain_with_redirections_still_records_pass(self, state_dir: Path) -> None:
        payload = {
            "tool_input": {"command": f"cd . && {BOARD_SUITE_CMD} > out.log 2>&1"},
            "tool_response": {"exit_code": 0},
        }
        _run_hook(AUTO_RECORD, payload, state_dir)
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
        assert ledger["test-board_os"]["status"] == "PASS"

    def test_non_suite_command_ignored(self, state_dir: Path) -> None:
        payload = {
            "tool_input": {"command": "echo hello"},
            "tool_response": {"exit_code": 0},
        }
        code, _ = _run_hook(AUTO_RECORD, payload, state_dir)
        assert code == 0
        assert not (state_dir / ".last-verify.json").exists()
