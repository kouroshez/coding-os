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


# --- TASK-587: policy-file write guard + shell-indirection force-push ------


@pytest.mark.parametrize(
    "cmd",
    [
        "echo bad > .coding-os/hub-settings.json",
        "echo bad >> .coding-os/hub-settings.json",
        "printf x | tee .coding-os/hub-settings.json",
        "cp /tmp/x.json .coding-os/hub-settings.json",
        "mv /tmp/x.json .coding-os/hub-settings.json",
        "sed -i s/pr/trunk/ .coding-os/hub-settings.json",
        "python3 -c \"open('.coding-os/hub-settings.json','w').write('{}')\"",
        "echo x > ./sub/../.coding-os/hub-settings.json",
    ],
)
def test_blocks_settings_policy_write(cmd: str) -> None:
    assert _run(cmd) == 2, f"should BLOCK policy write: {cmd}"


@pytest.mark.parametrize(
    "cmd",
    [
        "cat .coding-os/hub-settings.json",
        "jq . .coding-os/hub-settings.json",
        "cp .coding-os/hub-settings.json /tmp/backup.json",
        "python3 -c \"import json; json.load(open('.coding-os/hub-settings.json'))\"",
        "grep git_settings .coding-os/hub-settings.json",
        "echo x > .coding-os/other-file.json",
    ],
)
def test_allows_settings_read_and_other(cmd: str) -> None:
    assert _run(cmd) == 0, f"should ALLOW: {cmd}"


@pytest.mark.parametrize(
    "cmd",
    [
        "eval 'git push --force origin main'",
        "printf 'git push origin main --force' | sh",
        "eval 'git reset --hard'",
    ],
)
def test_blocks_indirection_wrapped_dangerous(cmd: str) -> None:
    assert _run(cmd) == 2, f"should BLOCK indirection-wrapped: {cmd}"
