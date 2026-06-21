"""Behavior tests for the warn-destructive-edit hook (friction before destruction).

Spec: docs/engineering/destructive-edit-guard.md
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "src" / "core" / "hooks" / "warn-destructive-edit.sh"
LOAD_BEARING_DOC = REPO_ROOT / "docs" / "00-index.md"  # under docs/, committed
NON_LOAD_BEARING = REPO_ROOT / "pyproject.toml"  # committed, not docs/ nor an enforce_context_on glob


def _run(payload: dict, env_extra: dict | None = None) -> tuple[int, str]:
    import os

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=15,
        cwd=str(REPO_ROOT),
        env=env,
    )
    return proc.returncode, proc.stderr.decode()


def _big_edit(file_path: Path, lines: int = 30) -> dict:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(file_path), "old_string": "line\n" * lines, "new_string": ""},
    }


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_large_deletion_of_load_bearing_warns() -> None:
    code, err = _run(_big_edit(LOAD_BEARING_DOC))
    assert code == 0
    assert "warning:" in err
    assert "destructive edit" in err
    assert "docs/00-index.md" in err
    assert "git show" in err  # provenance pull command is surfaced


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_small_edit_is_silent() -> None:
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(LOAD_BEARING_DOC), "old_string": "a\nb\n", "new_string": ""},
    }
    code, err = _run(payload)
    assert code == 0
    assert err.strip() == ""


@pytest.mark.skipif(not NON_LOAD_BEARING.is_file(), reason="fixture file absent")
def test_non_load_bearing_file_is_silent() -> None:
    code, err = _run(_big_edit(NON_LOAD_BEARING))
    assert code == 0
    assert err.strip() == ""


def test_write_new_file_is_silent() -> None:
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(REPO_ROOT / "docs" / "__nonexistent_guard_fixture__.md"), "content": ""},
    }
    code, err = _run(payload)
    assert code == 0
    assert err.strip() == ""


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_multiedit_summed_deletion_warns() -> None:
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(LOAD_BEARING_DOC),
            "edits": [
                {"old_string": "a\n" * 8, "new_string": ""},
                {"old_string": "b\n" * 8, "new_string": ""},
            ],
        },
    }
    code, err = _run(payload)
    assert code == 0
    assert "destructive edit" in err


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_strict_mode_blocks() -> None:
    code, err = _run(_big_edit(LOAD_BEARING_DOC), env_extra={"COS_DESTRUCTIVE_GUARD": "strict"})
    assert code == 2
    assert "BLOCKED" in err


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_off_mode_is_silent() -> None:
    code, err = _run(_big_edit(LOAD_BEARING_DOC), env_extra={"COS_DESTRUCTIVE_GUARD": "off"})
    assert code == 0
    assert err.strip() == ""


def test_malformed_stdin_fails_open() -> None:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=b"not json at all",
        capture_output=True,
        timeout=15,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_write_overwrite_existing_load_bearing_warns() -> None:
    # wholesale overwrite of a committed multi-line doc with a tiny body = destruction
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(LOAD_BEARING_DOC), "content": "x"}}
    code, err = _run(payload)
    assert code == 0
    assert "destructive edit" in err


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_warning_surfaces_the_exact_pull_commands() -> None:
    # guards against spec<->message drift: the message MUST carry the documented pull commands + provenance label
    code, err = _run(_big_edit(LOAD_BEARING_DOC))
    assert code == 0
    assert "last committed:" in err
    assert "git show " in err
    assert "git log -p -3 -- " in err


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_threshold_boundary() -> None:
    # exactly MIN_LINES (12) removed -> flagged; one fewer -> silent
    at_threshold = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(LOAD_BEARING_DOC), "old_string": "x\n" * 12, "new_string": ""},
    }
    code, err = _run(at_threshold)
    assert code == 0
    assert "destructive edit" in err

    below = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(LOAD_BEARING_DOC), "old_string": "x\n" * 11, "new_string": ""},
    }
    code, err = _run(below)
    assert code == 0
    assert err.strip() == ""


@pytest.mark.skipif(not LOAD_BEARING_DOC.is_file(), reason="fixture doc absent")
def test_min_lines_override_raises_the_bar() -> None:
    # a 30-line deletion is silent when the threshold is raised to 50
    code, err = _run(_big_edit(LOAD_BEARING_DOC), env_extra={"COS_DESTRUCTIVE_GUARD_MIN_LINES": "50"})
    assert code == 0
    assert err.strip() == ""
