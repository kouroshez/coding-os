"""cos_task_move, the learning-loop close, pick, wip, work-log, daily and retro."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _parse


def test_work_log_append(project: Path, conn: sqlite3.Connection):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="log me",
            swimlane="core",
            kind="feature",
        )
    )
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary="did a thing",
            agent_session="ses-claude-xyz",
        )
    )
    assert env["ok"] is True

    md_path = project / "docs" / "tasks" / "TASK-001-log-me.md"
    content = md_path.read_text(encoding="utf-8")
    assert "did a thing" in content
    assert "## Work Log" in content


def test_work_log_append_ignores_prose_mention_of_heading(
    project: Path,
    conn: sqlite3.Connection,
):
    """A `## Work Log` mention inside prose must not capture the append —
    the entry lands under the real heading, not above it."""
    import re as _re

    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="prose mention",
            swimlane="core",
            kind="feature",
        )
    )
    _parse(
        mcp_tools.cos_task_edit(
            conn,
            task_id="TASK-001",
            body=(
                "# TASK-001: prose mention\n\n"
                "**Outcome (one sentence):** test the heading anchor.\n\n"
                "## Acceptance (G/W/T)\n"
                "- **Given** a task whose `## Work Log` is appended, "
                "**When** it runs, **Then** ok.\n\n"
                "## Work Log\n"
            ),
        )
    )
    _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary="under the heading please",
        )
    )
    md_path = project / "docs" / "tasks" / "TASK-001-prose-mention.md"
    content = md_path.read_text(encoding="utf-8")
    head = _re.search(r"(?m)^## Work Log[ \t]*$", content)
    assert head is not None, content
    # The entry must sit AFTER the real heading, never in the prose above it.
    assert "under the heading please" in content[head.end() :]
    assert "under the heading please" not in content[: head.start()]


def test_work_log_truncates_long_summary(
    project: Path,
    conn: sqlite3.Connection,
):
    mcp_tools.cos_task_create(
        conn,
        title="trunc",
        swimlane="core",
        kind="chore",
    )
    long_summary = "x" * 500
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary=long_summary,
        )
    )
    assert env["ok"] is True
    # Line should be ≤ 120 chars of summary
    line = env["data"]["line_appended"]
    # Format: "- YYYY-MM-DD [agent]: xxx"
    summary_part = line.split(": ", 1)[1]
    assert len(summary_part) <= 120


def test_work_log_truncation_marks_loss_with_ellipsis(
    project: Path,
    conn: sqlite3.Connection,
):
    mcp_tools.cos_task_create(conn, title="ellipsis", swimlane="core", kind="chore")
    long_summary = "word " * 40  # 199 chars after strip, many word boundaries
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary=long_summary,
        )
    )
    summary_part = env["data"]["line_appended"].split(": ", 1)[1]
    assert len(summary_part) <= 120
    # The loss is marked, not silent.
    assert summary_part.endswith("…")
    # The cut fell on a word boundary, not mid-word.
    kept = summary_part[:-1].rstrip()
    assert long_summary.strip().startswith(kept)
    assert long_summary.strip()[len(kept)] == " "


def test_work_log_uses_readable_agent_label_from_session(
    project: Path,
    conn: sqlite3.Connection,
):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="label",
            swimlane="core",
            kind="feature",
        )
    )
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary="done",
            agent_session="ses-codex-20260423-abc",
        )
    )
    assert env["ok"] is True
    assert "[codex]" in env["data"]["line_appended"]
