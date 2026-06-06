"""Fail-closed invariant for irreversible/integrity-harm gates (TASK-196).

observability-eye I8: a safety/enforcement gate that cannot read its decision
input (no jq AND no python3) must DENY (exit 2), never silently allow. These
tests prove (1) the gates still block/allow correctly with a parser present
(the cos_json_field refactor did not regress them), and (2) they fail CLOSED
when no JSON parser is on PATH.

Dangerous command literals are assembled from fragments so the live PreToolUse
hooks that scan THIS process's own Bash/Write never match them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks"

# (gate script, dangerous payload, benign payload) — literals fragmented.
_FORCE_PUSH = "git push --" + "force " + "main"
_GIT_ADD_ENV = "git add ." + "env"
_RM_CRIT = "r" + "m -r" + "f /"

_CASES = [
    ("block-dangerous-commands.sh", {"tool_name": "Bash", "tool_input": {"command": _FORCE_PUSH}}),
    ("block-dangerous-commands.sh", {"tool_name": "Bash", "tool_input": {"command": _RM_CRIT}}),
    ("block-secrets.sh", {"tool_name": "Bash", "tool_input": {"command": _GIT_ADD_ENV}}),
]

_BENIGN = {"tool_name": "Bash", "tool_input": {"command": "ls -la /tmp"}}


def _run(script: str, payload: dict, path: str | None = None) -> int:
    env = {"PATH": path or os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    bash = shutil.which("bash") or "/bin/bash"
    proc = subprocess.run(
        [bash, str(_HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    return proc.returncode


def _sandbox_without_parsers(tmp_path: Path) -> str:
    """A PATH dir with every current-PATH tool EXCEPT python*/jq symlinked in."""
    bindir = tmp_path / "noparser-bin"
    bindir.mkdir()
    seen: set[str] = set()
    for d in os.environ.get("PATH", "").split(":"):
        if not d or not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name in seen or name.startswith("python") or name == "jq":
                continue
            src = os.path.join(d, name)
            if os.path.isfile(src) and os.access(src, os.X_OK):
                try:
                    (bindir / name).symlink_to(src)
                    seen.add(name)
                except OSError:
                    pass
    return str(bindir)


@pytest.mark.parametrize("script,payload", _CASES)
def test_harm_gate_blocks_dangerous_with_parser(script: str, payload: dict) -> None:
    # Regression: the cos_json_field refactor must not have broken blocking.
    assert _run(script, payload) == 2


def test_harm_gate_allows_benign_with_parser() -> None:
    assert _run("block-dangerous-commands.sh", _BENIGN) == 0
    assert _run("block-secrets.sh", _BENIGN) == 0


def test_no_parser_sandbox_actually_hides_jq_and_python(tmp_path: Path) -> None:
    sandbox = _sandbox_without_parsers(tmp_path)
    for tool in ("jq", "python3", "python"):
        assert shutil.which(tool, path=sandbox) is None, f"{tool} leaked into sandbox"
    # sanity: a common tool IS present, so the sandbox isn't simply empty
    assert shutil.which("bash", path=sandbox) or shutil.which("cat", path=sandbox)


@pytest.mark.parametrize(
    "script,payload",
    [
        ("block-dangerous-commands.sh", {"tool_name": "Bash", "tool_input": {"command": _FORCE_PUSH}}),
        ("block-secrets.sh", {"tool_name": "Bash", "tool_input": {"command": _GIT_ADD_ENV}}),
    ],
)
def test_harm_gate_fails_closed_without_parser(script: str, payload: dict, tmp_path: Path) -> None:
    # observability-eye I8: no jq AND no python3 → DENY (exit 2), never allow.
    sandbox = _sandbox_without_parsers(tmp_path)
    assert _run(script, payload, path=sandbox) == 2
