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

from database import init_db  # noqa: E402


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = init_db(str(tmp_path / "t.db"))
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def _add_trusted(connection: sqlite3.Connection, text: str) -> None:
    connection.execute(
        "INSERT INTO learned_patterns "
        "(pattern, memory_type, source, confidence, times_validated) "
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
    rows = conn.execute(
        "SELECT pattern FROM learned_patterns WHERE source = 'import'"
    ).fetchall()
    assert len(rows) == 1
    assert "Auth gotcha" in rows[0]["pattern"]
    ledger = json.loads((mem / sync.LEDGER_NAME).read_text(encoding="utf-8"))
    assert len(ledger) == 1
