"""enforce-task-readiness — a created card must declare its pull-state (TASK-1005).

Resolves DC-2. The condition was already detected by `warn-abandoned-task`, but
only at Stop — after the agent had told the operator the work was filed. These
tests pin the gate at creation, on both the MCP and the CLI surface.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "enforce-task-readiness.sh"

CREATE_TOOL = "mcp__coding-os__cos_task_create"


def _run(payload: dict) -> tuple[int, str]:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=20,
    )
    return proc.returncode, proc.stderr.decode(errors="ignore")


def _mcp(**tool_input) -> tuple[int, str]:
    return _run({"tool_name": CREATE_TOOL, "tool_input": tool_input})


def _bash(command: str) -> tuple[int, str]:
    return _run({"tool_name": "Bash", "tool_input": {"command": command}})


class TestMcpSurface:
    def test_blocks_a_create_with_no_pull_state(self) -> None:
        code, err = _mcp(title="x", swimlane="core", kind="bug")
        assert code == 2
        # A block without remediation leaves the agent guessing; all three exits
        # must be named, not just the one the hook happens to prefer.
        assert "ready=True" in err
        assert "parked" in err
        assert "keep" in err
        assert "task-lifecycle.md" in err

    def test_allows_ready_true(self) -> None:
        assert _mcp(title="x", ready=True)[0] == 0

    def test_allows_ready_as_a_string(self) -> None:
        # Some runtimes stringify booleans in tool args.
        assert _mcp(title="x", ready="true")[0] == 0

    def test_allows_parked_label(self) -> None:
        assert _mcp(title="x", labels=["parked"])[0] == 0

    def test_allows_keep_label(self) -> None:
        assert _mcp(title="x", labels=["infra", "keep"])[0] == 0

    def test_allows_a_non_icebox_status(self) -> None:
        # The invisibility failure is specific to un-ready icebox.
        assert _mcp(title="x", status="in_progress")[0] == 0

    def test_blocks_an_explicit_icebox_with_no_pull_state(self) -> None:
        assert _mcp(title="x", status="icebox")[0] == 2

    def test_unrelated_labels_do_not_count_as_a_declaration(self) -> None:
        assert _mcp(title="x", labels=["infra", "database"])[0] == 2


class TestCliSurface:
    """The CLI must not be a bypass for the same rule."""

    def test_blocks_task_create_without_ready(self) -> None:
        code, err = _bash("cos task-create --title x --swimlane core --kind bug")
        assert code == 2
        assert "--ready" in err

    def test_allows_ready_flag(self) -> None:
        assert _bash("cos task-create --title x --ready")[0] == 0

    def test_allows_parked_via_space_separated_labels(self) -> None:
        assert _bash("cos task-create --title x --labels parked")[0] == 0

    def test_allows_keep_via_equals_form(self) -> None:
        assert _bash("cos task-create --title x --labels=keep")[0] == 0

    def test_allows_a_non_icebox_status(self) -> None:
        assert _bash("cos task-create --title x --status in_progress")[0] == 0


class TestCommandPositionOnly:
    """The phrase as data is not an invocation — this one bit the hook's own commit."""

    def test_commit_message_mentioning_the_command_passes(self) -> None:
        # The first attempt at committing this very hook was blocked by its own
        # substring match. An enforcement hook that fires on prose about a
        # command is one operators learn to route around.
        assert (
            _bash('git commit -m "feat: gate cos_task_create and cos task-create surfaces"')[0] == 0
        )

    def test_grepping_for_the_command_passes(self) -> None:
        assert _bash("grep -rn 'cos task-create' docs/")[0] == 0

    def test_echoing_the_command_passes(self) -> None:
        assert _bash("echo 'run cos task-create --title x to file a card'")[0] == 0

    def test_still_blocks_a_real_invocation_after_an_operator(self) -> None:
        code, _ = _bash("git status && cos task-create --title x")
        assert code == 2

    def test_still_blocks_behind_an_env_prefix(self) -> None:
        assert _bash("env COS_AGENT=claude cos task-create --title x")[0] == 2

    def test_allows_a_ready_invocation_after_an_operator(self) -> None:
        assert _bash("git status && cos task-create --title x --ready")[0] == 0

    def test_blocks_when_any_chained_create_is_un_ready(self) -> None:
        code, _ = _bash("cos task-create --title a --ready; cos task-create --title b")
        assert code == 2


class TestNoCollateralDamage:
    """It rides the Bash matcher, so it must be invisible to everything else."""

    def test_ordinary_bash_passes(self) -> None:
        for command in (
            "ls -la",
            "git status",
            "uv run pytest -q",
            "cos board",
            "cos task-ready X",
        ):
            assert _bash(command)[0] == 0, command

    def test_other_task_tools_pass(self) -> None:
        assert (
            _run({"tool_name": "mcp__coding-os__cos_task_move", "tool_input": {"to": "icebox"}})[0]
            == 0
        )

    def test_malformed_payload_fails_open(self) -> None:
        # warn-abandoned-task remains the Stop-time backstop, so degrading to the
        # previous behaviour beats blocking every task creation.
        proc = subprocess.run(
            ["bash", str(HOOK)], input=b"not json", capture_output=True, timeout=20
        )
        assert proc.returncode == 0
