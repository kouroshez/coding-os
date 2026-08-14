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
from memory_gc import TRASH_PATH_PREFIXES, gc_memory


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


class TestOrphanReconcile:
    """gc_memory deletes referential-integrity orphans that CASCADE missed:
    orphan embeddings (learned_patterns), pattern_validations, graph_evidence."""

    def test_reconciles_all_orphan_classes(self, tmp_path: Path) -> None:
        db = tmp_path / "g.db"
        c = init_db(db)
        # valid parent rows
        # Seed with FK off — mirrors the backend bulk-write path AND lets us
        # construct the exact orphan states (dangling edge_id, deleted parent)
        # that the reconcile must clean. gc_memory reconciles with FK on.
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute(
            "INSERT INTO learned_patterns (id, pattern, memory_type, source, confidence) "
            "VALUES (1, 'p', 'lesson', 'friction', 0.6)"
        )
        c.execute(
            "INSERT INTO graph_edges_v12 (id, source_id, target_id, edge_type, extractor, created_at, updated_at) "
            "VALUES (1, 1, 2, 'calls', 'test', 0, 0)"
        )
        c.execute(
            "INSERT INTO graph_evidence_v12 (edge_id, signal_name, weight, created_at) VALUES (1,'s',1.0,0)"
        )
        c.execute(
            "INSERT INTO graph_evidence_v12 (edge_id, signal_name, weight, created_at) VALUES (99999,'s',1.0,0)"
        )
        c.execute(
            "INSERT INTO embeddings (source_table, source_id, text_hash, embedding) "
            "VALUES ('learned_patterns', 999, 'h', X'00')"
        )
        c.execute(
            "INSERT INTO pattern_validations (session_id, pattern_id, was_helpful) VALUES ('s', 999, 1)"
        )
        c.commit()
        c.close()

        stats = gc_memory(db)
        assert stats["orphan_embeddings_learned_patterns"] == 1
        assert stats["orphan_pattern_validations"] == 1
        assert stats["orphan_graph_evidence"] == 1

        c2 = sqlite3.connect(db)
        assert c2.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0
        assert c2.execute("SELECT COUNT(*) FROM pattern_validations").fetchone()[0] == 0
        assert (
            c2.execute("SELECT COUNT(*) FROM graph_evidence_v12").fetchone()[0] == 1
        )  # valid kept
        c2.close()

    def test_sweeps_outbox_rows_whose_source_was_reaped(self, tmp_path: Path) -> None:
        # The changelog TTL reaps observations the outbox still queues. The drain
        # only clears `limit` rows per session, so orphans accumulate faster than
        # they are consumed and starve the real rows behind them.
        db = tmp_path / "outbox.db"
        c = init_db(db)
        c.execute(
            "INSERT INTO observations (id, session_id, title, narrative, memory_type) "
            "VALUES (1, 's', 'kept', 'n', 'changelog')"
        )
        for source_id in (1, 404, 405):
            c.execute(
                "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
                "VALUES ('observations', ?, 0)",
                (source_id,),
            )
        c.commit()
        c.close()

        stats = gc_memory(db)

        assert stats["orphan_outbox_rows"] == 2
        c2 = sqlite3.connect(db)
        surviving = c2.execute("SELECT source_id FROM embedding_outbox").fetchall()
        c2.close()
        assert surviving == [(1,)]

    def test_outbox_sweep_runs_after_the_deletes_that_orphan_rows(self, tmp_path: Path) -> None:
        # Ordering guard: step 3 deletes trash observations, so a sweep placed
        # before it leaves the rows it just orphaned for the next run.
        db = tmp_path / "order.db"
        c = init_db(db)
        c.execute(
            "INSERT INTO observations (id, session_id, title, narrative, memory_type, files_modified) "
            "VALUES (1, 's', 'trash', 'n', 'changelog', ?)",
            (f"{TRASH_PATH_PREFIXES[0]}sample.py",),
        )
        c.execute(
            "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 1, 0)"
        )
        c.commit()
        c.close()

        stats = gc_memory(db)

        assert stats["trash_observations"] == 1
        assert stats["orphan_outbox_rows"] == 1, "sweep ran before the trash delete"
        c2 = sqlite3.connect(db)
        assert c2.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0] == 0
        c2.close()

    def test_dry_run_counts_outbox_orphans_without_deleting(self, tmp_path: Path) -> None:
        db = tmp_path / "outbox_dry.db"
        c = init_db(db)
        c.execute(
            "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 404, 0)"
        )
        c.commit()
        c.close()

        stats = gc_memory(db, dry_run=True)

        assert stats["orphan_outbox_rows"] == 1
        c2 = sqlite3.connect(db)
        assert c2.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0] == 1
        c2.close()
