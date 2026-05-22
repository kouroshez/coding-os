"""TASK-010 Group D — `_assign_guard` for board moves.

A task with no `assignee:` frontmatter is movable by anyone (default).
When `assignee` is set, only that session or another session of the
same agent may move it; `force` / `COS_ASSIGN_OVERRIDE` bypass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from board_os.mcp_tools import _assign_guard


def _task(tmp_path: Path, assignee: str | None) -> Path:
    fm = "---\nid: TASK-001\nstatus: in_progress\n"
    if assignee is not None:
        fm += f"assignee: {assignee}\n"
    fm += "---\n\n# TASK-001\n"
    path = tmp_path / "TASK-001.md"
    path.write_text(fm, encoding="utf-8")
    return path


def test_no_assignee_allows_anyone(tmp_path: Path) -> None:
    assert _assign_guard(_task(tmp_path, None), "ses-codex-x", force=False) is None


@pytest.mark.parametrize("sentinel", ["any", "anyone", "unassigned"])
def test_unassigned_sentinel_allows(tmp_path: Path, sentinel: str) -> None:
    assert _assign_guard(_task(tmp_path, sentinel), "ses-codex-x", force=False) is None


def test_same_session_allowed(tmp_path: Path) -> None:
    path = _task(tmp_path, "ses-claude-123")
    assert _assign_guard(path, "ses-claude-123", force=False) is None


def test_same_agent_other_session_allowed(tmp_path: Path) -> None:
    path = _task(tmp_path, "ses-claude-aaa")
    assert _assign_guard(path, "ses-claude-bbb", force=False) is None


def test_cross_agent_blocked(tmp_path: Path) -> None:
    msg = _assign_guard(_task(tmp_path, "ses-claude-aaa"), "ses-codex-bbb", force=False)
    assert msg is not None
    assert "assigned to" in msg


def test_force_bypasses(tmp_path: Path) -> None:
    path = _task(tmp_path, "ses-claude-aaa")
    assert _assign_guard(path, "ses-codex-bbb", force=True) is None


def test_env_override_bypasses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COS_ASSIGN_OVERRIDE", "1")
    path = _task(tmp_path, "ses-claude-aaa")
    assert _assign_guard(path, "ses-codex-bbb", force=False) is None


def test_missing_file_allows(tmp_path: Path) -> None:
    assert _assign_guard(tmp_path / "nope.md", "ses-codex-x", force=False) is None
