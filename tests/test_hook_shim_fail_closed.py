"""Without a coding-os install the hook shim fails blocking hooks closed and observers open.

Spec: docs/engineering/harness-loading-audit-2026-11.md § Gates (G3).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SHIM = REPO / "src" / "core" / "scripts" / "hook-shim.sh"
REGISTRY = REPO / "src" / "core" / "hooks" / "registry.yaml"
NO_COS_PATH = "/usr/bin:/bin"


def _shim_blocking() -> set[str]:
    match = re.search(r'^BLOCKING_HOOKS="([^"]*)"', SHIM.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "hook-shim.sh lost its BLOCKING_HOOKS list"
    return set(match.group(1).split())


def _run_hook(
    consumer: Path, hook: str, payload: dict, **env: str
) -> subprocess.CompletedProcess[str]:
    link = consumer / ".claude" / "hooks" / f"{hook}.sh"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to("../../.coding-os/hook-shim.sh")
    return subprocess.run(
        ["/bin/bash", str(link)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": NO_COS_PATH, "HOME": str(consumer), **env},
        timeout=10,
    )


@pytest.fixture()
def consumer(tmp_path: Path) -> Path:
    assert shutil.which("cos", path=NO_COS_PATH) is None
    (tmp_path / ".coding-os").mkdir()
    shutil.copy2(SHIM, tmp_path / ".coding-os" / "hook-shim.sh")
    return tmp_path


def test_shim_list_is_the_registry_blocking_set_and_its_dispatchers() -> None:
    hooks = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["hooks"]
    blocking = {hook["id"] for hook in hooks if hook.get("blocking")}
    dispatchers = {
        dispatcher["script"].removesuffix(".sh")
        for adapter in (REPO / "src" / "adapters").glob("*/adapter.yaml")
        for dispatcher in yaml.safe_load(adapter.read_text(encoding="utf-8")).get(
            "hook_dispatchers"
        )
        or []
        if blocking & {name.removesuffix(".sh") for name in dispatcher.get("delegates") or []}
    }
    assert dispatchers, "no adapter dispatcher fronts a blocking hook"
    assert _shim_blocking() == blocking | dispatchers


def test_a_blocking_hook_blocks_with_an_install_hint(consumer: Path) -> None:
    proc = _run_hook(consumer, "block-secrets", {"tool_input": {"command": "ls"}})
    assert proc.returncode == 2
    assert "uv tool install coding-os" in proc.stderr


def test_the_bootstrap_escape_lets_the_install_command_through(consumer: Path) -> None:
    payload = {"tool_input": {"command": "uv tool install coding-os"}}
    proc = _run_hook(consumer, "block-secrets", payload, COS_ALLOW_MISSING_DEPS="1")
    assert proc.returncode == 0


def test_an_observer_hook_exits_zero(consumer: Path) -> None:
    proc = _run_hook(consumer, "record-verify-auto", {"tool_input": {"command": "ls"}})
    assert (proc.returncode, proc.stderr) == (0, "")


def test_a_codex_dispatcher_of_blocking_hooks_blocks(consumer: Path) -> None:
    proc = _run_hook(consumer, "codex-pretool-dispatch", {"tool_input": {"command": "ls"}})
    assert proc.returncode == 2
    assert "uv tool install coding-os" in proc.stderr


def test_a_blocking_stop_hook_lets_a_retried_stop_through(consumer: Path) -> None:
    payload = {"hook_event_name": "Stop", "stop_hook_active": True}
    proc = _run_hook(consumer, "enforce-humanizer-audit", payload)
    assert proc.returncode == 0


def test_the_stop_retry_escape_is_ignored_outside_stop(consumer: Path) -> None:
    payload = {"hook_event_name": "PreToolUse", "tool_input": {"stop_hook_active": True}}
    proc = _run_hook(consumer, "enforce-task-readiness", payload)
    assert proc.returncode == 2
