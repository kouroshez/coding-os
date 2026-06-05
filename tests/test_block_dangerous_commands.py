"""Behavior tests for block-dangerous-commands.sh (audit N2 / 2a rm-rf, 2c force-push)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOK = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "core"
    / "hooks"
    / "block-dangerous-commands.sh"
)


def _run(command: str) -> int:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=10,
    )
    return proc.returncode


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf /",
        "rm -rf .",
        "rm -rf ..",
        "rm -rf ./",
        "rm -rf *",
        "rm -fr backend",
        "rm -r -f /",
        "rm -rf /etc",
        "sudo rm -rf /",
        "cd /tmp && rm -rf /",
        "rm -rf ~",
    ],
)
def test_blocks_dangerous_rm(cmd: str) -> None:
    assert _run(cmd) == 2, f"should BLOCK: {cmd}"


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf ./build/cache",
        "rm -f somefile.txt",
        "rm -rf node_modules",
        "rm tmp.log",
        "ls -la",
    ],
)
def test_allows_safe_commands(cmd: str) -> None:
    assert _run(cmd) == 0, f"should ALLOW: {cmd}"


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin +main",
        "git push origin +HEAD:main",
        "git push --force origin main",
    ],
)
def test_blocks_force_push_main(cmd: str) -> None:
    assert _run(cmd) == 2, f"should BLOCK force-push: {cmd}"
