"""Concept-graph bound contract: bounded co_edit fan-out + stale-edge GC prune.

Regression guard for the 260 MB incident — an unbounded O(N^2) co_edit graph.
Contract: docs/engineering/concept-graph.md.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from graph import record_co_edit
from memory_gc import gc_memory


@pytest.fixture
def conn(tmp_path: Path):
    c = init_db(tmp_path / "t.db")
    yield c
    c.close()


def _obs(conn: sqlite3.Connection, session: str, fpath: str, ts: str) -> None:
    conn.execute(
        "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
        "impact_score, title, narrative, content_hash, files_modified, created_at) "
        "VALUES (?, 'Edit', 'edit', 'discovery', 0.5, 't', 'n', ?, ?, ?)",
        (session, f"h-{fpath}-{ts}", fpath, ts),
    )


class TestCoEditFanoutCap:
    def test_fanout_capped_to_max_links(self, conn: sqlite3.Connection) -> None:
        sess = "ses-x"
        for i in range(12):
            _obs(conn, sess, f"/r/file{i:02d}.py", f"2026-06-07 10:{i:02d}:00")
        conn.commit()
        edges = record_co_edit(conn, session_id=sess, file_path="/r/new.py", max_links=8)
        assert len(edges) == 8  # capped — not 12 (no O(N^2) blowup)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM concept_graph WHERE edge_type='co_edit'"
        ).fetchone()[0]
        assert cnt == 8

    def test_fanout_picks_most_recent(self, conn: sqlite3.Connection) -> None:
        sess = "ses-y"
        for i in range(10):
            _obs(conn, sess, f"/r/f{i}.py", f"2026-06-07 10:{i:02d}:00")
        conn.commit()
        record_co_edit(conn, session_id=sess, file_path="/r/new.py", max_links=3)
        rows = conn.execute(
            "SELECT source, target FROM concept_graph WHERE edge_type='co_edit'"
        ).fetchall()
        linked = {x for r in rows for x in (r[0], r[1]) if x != "/r/new.py"}
        assert "/r/f9.py" in linked  # most recent kept
        assert "/r/f0.py" not in linked  # oldest dropped by the cap


class TestCoEditGcPrune:
    def test_stale_weak_edges_pruned(self, tmp_path: Path) -> None:
        db = tmp_path / "g.db"
        c = init_db(db)
        c.execute(  # stale + weak → pruned
            "INSERT INTO concept_graph (source, target, edge_type, weight, updated_at) "
            "VALUES ('a','b','co_edit',1.0, datetime('now','-60 days'))"
        )
        c.execute(  # reinforced (weight>1) though old → kept
            "INSERT INTO concept_graph (source, target, edge_type, weight, updated_at) "
            "VALUES ('c','d','co_edit',2.0, datetime('now','-60 days'))"
        )
        c.execute(  # weak but recent → kept
            "INSERT INTO concept_graph (source, target, edge_type, weight, updated_at) "
            "VALUES ('e','f','co_edit',1.0, datetime('now','-1 days'))"
        )
        c.commit()
        c.close()

        stats = gc_memory(db)
        assert stats["stale_co_edit_edges"] == 1

        c2 = sqlite3.connect(db)
        remaining = c2.execute("SELECT COUNT(*) FROM concept_graph").fetchone()[0]
        c2.close()
        assert remaining == 2  # reinforced + recent survive
