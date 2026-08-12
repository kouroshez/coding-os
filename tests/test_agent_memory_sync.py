"""Versioned agent memory: mirror rendering, no-clobber, harvest dedup."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
THINKING_OS = REPO_ROOT / "src" / "core" / "thinking_os"
HELPER = REPO_ROOT / "src" / "adapters" / "claude" / "hooks" / "agent_memory_sync.py"

if str(THINKING_OS) not in sys.path:
    sys.path.insert(0, str(THINKING_OS))

spec = importlib.util.spec_from_file_location("agent_memory_sync", HELPER)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

from database import init_db


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = init_db(str(tmp_path / "t.db"))
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def _add_trusted(connection: sqlite3.Connection, text: str) -> None:
    connection.execute(
        "INSERT INTO learned_patterns "
        "(pattern, memory_type, source, confidence, times_seen) "
        "VALUES (?, 'lesson', 'friction', 0.8, 4)",
        (text,),
    )
    connection.commit()


def test_mirror_renders_trusted_and_preserves_manual_notes(conn, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("## My manual note\nkeep me\n", encoding="utf-8")
    _add_trusted(conn, "Use git show branch:path instead of worktrees in trunk mode")

    sync.render_mirror(mem, sync._trusted_lessons(conn))

    content = (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert "cos:generated:start" in content
    assert "git show branch:path" in content
    assert "keep me" in content
    assert "_(seen 4×)_" in content
    assert "_(validated" not in content


def test_mirror_rerender_updates_block_only(conn, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("manual tail\n", encoding="utf-8")
    _add_trusted(conn, "first lesson text for the mirror block")
    sync.render_mirror(mem, sync._trusted_lessons(conn))
    _add_trusted(conn, "second lesson text arrives later on")
    sync.render_mirror(mem, sync._trusted_lessons(conn))

    content = (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert content.count("cos:generated:start") == 1
    assert "second lesson text" in content
    assert "manual tail" in content


def _add_pattern(connection: sqlite3.Connection, text: str, confidence: float, seen: int) -> None:
    connection.execute(
        "INSERT INTO learned_patterns "
        "(pattern, memory_type, source, confidence, times_seen) "
        "VALUES (?, 'lesson', 'friction', ?, ?)",
        (text, confidence, seen),
    )
    connection.commit()


def test_mirror_drops_placeholder_lessons_and_keeps_distilled(conn) -> None:
    # The placeholder's confidence outranks the distilled lesson (recurrence
    # lifts it), so ranking alone would render the counter and hide the lesson.
    _add_pattern(
        conn,
        "Recurring block (144 occurrences): block-secrets — no-verify "
        "→ satisfy the blocked rule before retrying the action",
        0.85,
        144,
    )
    _add_pattern(
        conn,
        "Recurring error (5 occurrences): reading a 400KB file at once "
        "→ fix the failing precondition before retrying",
        0.80,
        5,
    )
    _add_pattern(
        conn,
        "Passing multi-line scripts to uv run via a bash heredoc deadlocks "
        "→ write the script to a file and run it",
        0.50,
        4,
    )

    rendered = [row["pattern"] for row in sync._trusted_lessons(conn)]

    assert len(rendered) == 1
    assert "heredoc" in rendered[0]


def test_mirror_caps_the_block_at_the_declared_budget(conn) -> None:
    for index in range(sync.MIRROR_LESSON_LIMIT + 7):
        _add_pattern(conn, f"distilled lesson number {index} with a real remediation", 0.5, 3)

    assert len(sync._trusted_lessons(conn)) == sync.MIRROR_LESSON_LIMIT


def test_harvest_never_mints_from_the_index_file(conn, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _add_trusted(conn, "a real lesson that the mirror exports into the block")
    sync.render_mirror(mem, sync._trusted_lessons(conn))
    # The human index below the generated block: headings, links, no prose.
    with (mem / "MEMORY.md").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n# Memory Index\n"
            "- [Sample lesson](sample.md) — one line hook for the note\n"
            "- [Another lesson](another.md) — one line hook for the note\n"
        )

    assert sync.harvest(mem, conn) == 0
    assert (
        conn.execute("SELECT COUNT(*) FROM learned_patterns WHERE source='import'").fetchone()[0]
        == 0
    )


def test_harvest_mints_once_and_skips_generated_block(conn, tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _add_trusted(conn, "exported trusted lesson that must not be re-imported")
    sync.render_mirror(mem, sync._trusted_lessons(conn))
    (mem / "notes.md").write_text(
        "## Auth gotcha discovered by the harness\n"
        "The OTP endpoint drops waitUntil on cold starts, so resend explicitly.\n",
        encoding="utf-8",
    )

    first = sync.harvest(mem, conn)
    second = sync.harvest(mem, conn)

    assert first == 1
    assert second == 0
    rows = conn.execute("SELECT pattern FROM learned_patterns WHERE source = 'import'").fetchall()
    assert len(rows) == 1
    assert "Auth gotcha" in rows[0]["pattern"]
    ledger = json.loads((mem / sync.LEDGER_NAME).read_text(encoding="utf-8"))
    assert len(ledger) == 1
