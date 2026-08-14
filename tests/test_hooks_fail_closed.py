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
import re
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


def _sandbox_without(tmp_path: Path, *hidden: str) -> str:
    """A PATH dir with every current-PATH tool symlinked in except `hidden`.

    `python` hides every python* interpreter; other names match exactly.
    """
    bindir = tmp_path / ("bin-no-" + "-".join(hidden))
    bindir.mkdir()
    seen: set[str] = set()
    for d in os.environ.get("PATH", "").split(":"):
        if not d or not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name in seen:
                continue
            if any(name.startswith("python") if h == "python" else name == h for h in hidden):
                continue
            src = os.path.join(d, name)
            if os.path.isfile(src) and os.access(src, os.X_OK):
                try:
                    (bindir / name).symlink_to(src)
                    seen.add(name)
                except OSError:
                    pass
    return str(bindir)


def _sandbox_without_parsers(tmp_path: Path) -> str:
    return _sandbox_without(tmp_path, "python", "jq")


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
        (
            "block-dangerous-commands.sh",
            {"tool_name": "Bash", "tool_input": {"command": _FORCE_PUSH}},
        ),
        ("block-secrets.sh", {"tool_name": "Bash", "tool_input": {"command": _GIT_ADD_ENV}}),
    ],
)
def test_harm_gate_fails_closed_without_parser(script: str, payload: dict, tmp_path: Path) -> None:
    # observability-eye I8: no jq AND no python3 → DENY (exit 2), never allow.
    sandbox = _sandbox_without_parsers(tmp_path)
    assert _run(script, payload, path=sandbox) == 2


# --- degraded-toolchain matrix: same verdict with a tool missing, not the floor ---

_DEGRADED = [
    pytest.param("jq", id="no-jq"),
    pytest.param("perl", id="no-perl"),
]


@pytest.mark.parametrize("missing", _DEGRADED)
@pytest.mark.parametrize("script,payload", _CASES)
def test_harm_gate_same_verdict_when_one_tool_missing(
    script: str, payload: dict, missing: str, tmp_path: Path
) -> None:
    """I8: hiding jq or perl must not change a BLOCK into an allow.

    perl is the one that bit us: `cos_read_stdin_bounded` was perl-only and
    ended in `|| true`, so a perl-less image handed every gate an empty
    envelope and every gate took its no-op branch.
    """
    sandbox = _sandbox_without(tmp_path, missing)
    assert shutil.which(missing, path=sandbox) is None, f"{missing} leaked into sandbox"
    assert _run(script, payload, path=sandbox) == 2


@pytest.mark.parametrize("missing", _DEGRADED)
def test_harm_gate_still_allows_benign_when_one_tool_missing(
    missing: str, tmp_path: Path
) -> None:
    sandbox = _sandbox_without(tmp_path, missing)
    assert _run("block-dangerous-commands.sh", _BENIGN, path=sandbox) == 0
    assert _run("block-secrets.sh", _BENIGN, path=sandbox) == 0


# `_cos_env_io.sh` IS the jq fast path, and `cos-env.sh` reads hub-settings.json
# behind its own explicit `command -v jq` / python3 branch.
_JQ_IMPLEMENTORS = {"_cos_env_io.sh", "cos-env.sh"}
_BLOCKS = re.compile(r"^\s*exit\s+2\b", re.M)
_RAW_JQ = re.compile(r"(?<![\w-])jq\s+(-[a-zA-Z]+\s+)*['\"]?\.")


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def test_no_blocking_hook_extracts_fields_with_raw_jq() -> None:
    """A gate that reads its input with bare jq flips its verdict when jq is absent.

    `jq -r … || echo ""` yields empty (gate no-ops, exit 0) and a bare
    `jq -r … ` yields 127, which is not 2, so the runtime lets the call through.
    Every gate must extract through cos_json_field, which degrades to python3.
    """
    offenders: list[str] = []
    for path in sorted(_HOOKS.glob("*.sh")):
        if path.name in _JQ_IMPLEMENTORS:
            continue
        body = path.read_text()
        if not _BLOCKS.search(body):
            continue
        for line in _code_lines(body):
            if _RAW_JQ.search(line):
                offenders.append(f"{path.name}: {line.strip()[:90]}")
    assert not offenders, "blocking hooks still parsing with raw jq:\n  " + "\n  ".join(offenders)


_ENVELOPE = json.dumps(
    {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "docs/x.md",
            "edits": [{"old_string": "ALPHA"}, {"old_string": "BETA"}],
        },
    }
)

_FIELD_CASES = [
    ("tool_name", "MultiEdit"),
    ("tool_input.file_path", "docs/x.md"),
    ("tool_input.edits.0.old_string", "ALPHA"),
    ("tool_input.old_string tool_input.edits.0.old_string", "ALPHA"),
    ("absent.key", ""),
]


def _json_field(args: str, path: str | None = None) -> str:
    bash = shutil.which("bash") or "/bin/bash"
    proc = subprocess.run(
        [bash, "-c", f'source "{_HOOKS}/cos-env.sh" >/dev/null 2>&1; cos_json_field {args}'],
        input=_ENVELOPE,
        capture_output=True,
        text=True,
        env={"PATH": path or os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
        timeout=20,
    )
    return proc.stdout.strip()


@pytest.mark.parametrize("args,expected", _FIELD_CASES)
def test_json_field_jq_and_python_agree(args: str, expected: str, tmp_path: Path) -> None:
    """The jq fast path and the python3 fallback must be interchangeable.

    They drifted once: the jq branch builds a filter string, so array indices
    need `[0]` while the python branch walks segments — a path that worked
    under python silently returned the wrong subtree under jq.
    """
    assert _json_field(args) == expected
    assert _json_field(args, path=_sandbox_without(tmp_path, "jq")) == expected


def test_stdin_reader_survives_without_perl(tmp_path: Path) -> None:
    """The python3 fallback in cos_read_stdin_bounded actually returns the payload."""
    sandbox = _sandbox_without(tmp_path, "perl")
    bash = shutil.which("bash") or "/bin/bash"
    script = f'source "{_HOOKS}/cos-env.sh" >/dev/null 2>&1; cos_read_stdin_bounded 2'
    proc = subprocess.run(
        [bash, "-c", script],
        input='{"tool_name":"Bash"}',
        capture_output=True,
        text=True,
        env={"PATH": sandbox, "HOME": os.environ.get("HOME", "")},
        timeout=20,
    )
    assert '"tool_name"' in proc.stdout, f"empty envelope without perl: {proc.stdout!r}"


def _run_with_helper_dropped(hook: str, payload: dict, drop_helper: str, tmp_path: Path) -> int:
    """Copy the hooks tree to tmp, delete one _helpers/*.py, run the hook.

    Isolates COS_STATE_DIR so the gate never reads the real repo's governance
    markers and reaches the helper-missing branch deterministically (A2).
    """
    htmp = tmp_path / "hooks"
    shutil.copytree(_HOOKS, htmp)
    (htmp / "_helpers" / drop_helper).unlink(missing_ok=True)
    state = tmp_path / "state"
    state.mkdir()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "COS_STATE_DIR": str(state),
        "COS_GIT_WORKFLOW": "trunk",
    }
    bash = shutil.which("bash") or "/bin/bash"
    proc = subprocess.run(
        [bash, str(htmp / hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    return proc.returncode


def test_branch_guard_fails_closed_when_helper_missing(tmp_path: Path) -> None:
    # A git-related command past the fast-skip + helper gone = cannot verify -> DENY.
    payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert (
        _run_with_helper_dropped("branch-guard.sh", payload, "branch_guard_check.py", tmp_path) == 2
    )


def test_enforce_task_transition_fails_closed_when_helper_missing(tmp_path: Path) -> None:
    # A task-md edit + helper gone = cannot tell a status hand-edit from a body edit -> DENY.
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "docs/tasks/TASK-001-x.md",
            "old_string": "x",
            "new_string": "y",
        },
    }
    assert (
        _run_with_helper_dropped(
            "enforce-task-transition.sh", payload, "detect_status_transition.py", tmp_path
        )
        == 2
    )
