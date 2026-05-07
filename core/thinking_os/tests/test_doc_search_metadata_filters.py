"""Phase O — Stage-1 metadata pre-filter tests for cos_doc_search.

Covers migration v22 columns (domain/layer/ssot/updated_iso/is_active),
the doc_audit_trail → is_active flip wired into audit_log_record, and
the query-time hint extraction + active-task context helpers.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from database import run_migrations  # type: ignore
from doc_indexer import _parse_front_matter  # type: ignore
from tools.audit import audit_log_record  # type: ignore
from tools.docs import (  # type: ignore
    _active_task_context,
    _build_metadata_filter,
    _suggest_filters_from_query,
    doc_search,
)


# ---------------------------------------------------------------------------
# Fixture — minimal in-memory DB with hand-seeded chunks (no embeddings).
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    rows = [
        # (path, source_type, idx, heading, content, hash, prio, mtime,
        #  domain, layer, ssot, updated_iso, is_active)
        ("docs/a.md", "engineering", 0, "A > overview",
         "audit log doc edit history", "h1", 0.5, 1000,
         "OPS", "reference", "true", "2026-04-28", 1),
        ("docs/b.md", "playbook", 0, "B > steps",
         "audit log review playbook for governance", "h2", 0.5, 1000,
         "OPS", "playbook", "true", "2026-01-15", 1),
        ("docs/c.md", "engineering", 0, "C > legacy",
         "audit log legacy spec older era", "h3", 0.5, 1000,
         "BACKEND", "reference", "true", "2025-09-01", 1),
        ("docs/d.md", "adr", 0, "D > superseded",
         "audit log decision superseded by newer ADR", "h4", 0.5, 1000,
         "OPS", "adr", "true", "2024-06-01", 0),  # already inactive
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO document_chunks "
            "(source_path, source_type, chunk_index, heading_path, content, "
            " content_hash, priority, mtime, domain, layer, ssot, updated_iso, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            r,
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# _build_metadata_filter — pure unit
# ---------------------------------------------------------------------------

class TestMetadataFilter:
    def test_no_filter_returns_active_only(self):
        clause, params = _build_metadata_filter(
            source_types=None, domain=None, layer=None, since_iso=None,
            include_inactive=False,
        )
        assert "is_active" in clause
        assert params == []

    def test_domain_only(self):
        clause, params = _build_metadata_filter(
            source_types=None, domain="OPS", layer=None, since_iso=None,
            include_inactive=False,
        )
        assert "domain = ?" in clause
        assert "OPS" in params

    def test_combined_filters(self):
        clause, params = _build_metadata_filter(
            source_types=["adr"], domain="OPS", layer="reference",
            since_iso="2026-01-01", include_inactive=False,
        )
        assert "source_type IN (?)" in clause
        assert "domain = ?" in clause
        assert "layer = ?" in clause
        assert "updated_iso >= ?" in clause
        assert "is_active = 1" in clause
        assert params == ["adr", "OPS", "reference", "2026-01-01"]

    def test_include_inactive_drops_active_clause(self):
        clause, params = _build_metadata_filter(
            source_types=None, domain=None, layer=None, since_iso=None,
            include_inactive=True,
        )
        assert clause == ""
        assert params == []

    def test_table_alias(self):
        clause, params = _build_metadata_filter(
            source_types=None, domain="OPS", layer=None, since_iso=None,
            include_inactive=False, table_alias="dc",
        )
        assert "dc.domain = ?" in clause
        assert "dc.is_active" in clause


# ---------------------------------------------------------------------------
# doc_search — staged pre-filter behavior
# ---------------------------------------------------------------------------

class TestDocSearchFilters:
    def test_default_hides_inactive(self, seeded_conn):
        # docs/d.md is_active=0 — must NOT surface in default search.
        results = doc_search(seeded_conn, "audit log", limit=10, mode="lexical")
        paths = {r["source_path"] for r in results}
        assert "docs/d.md" not in paths
        assert "docs/a.md" in paths

    def test_include_inactive_surfaces_superseded(self, seeded_conn):
        results = doc_search(
            seeded_conn, "audit log", limit=10, mode="lexical",
            include_inactive=True,
        )
        paths = {r["source_path"] for r in results}
        assert "docs/d.md" in paths

    def test_domain_pre_filter(self, seeded_conn):
        results = doc_search(
            seeded_conn, "audit log", limit=10, mode="lexical",
            domain="BACKEND",
        )
        paths = {r["source_path"] for r in results}
        assert paths == {"docs/c.md"}

    def test_layer_pre_filter(self, seeded_conn):
        results = doc_search(
            seeded_conn, "audit log", limit=10, mode="lexical",
            layer="playbook",
        )
        paths = {r["source_path"] for r in results}
        assert paths == {"docs/b.md"}

    def test_since_iso_drops_old_docs(self, seeded_conn):
        # 2026-04-01 cutoff drops b (2026-01-15) and c (2025-09-01).
        results = doc_search(
            seeded_conn, "audit log", limit=10, mode="lexical",
            since_iso="2026-04-01",
        )
        paths = {r["source_path"] for r in results}
        assert paths == {"docs/a.md"}

    def test_combined_filters_intersect(self, seeded_conn):
        results = doc_search(
            seeded_conn, "audit log", limit=10, mode="lexical",
            domain="OPS", layer="reference",
        )
        paths = {r["source_path"] for r in results}
        # a is OPS+reference+active; d is OPS+adr (excluded by layer);
        # b is OPS+playbook (excluded by layer); c is BACKEND (excluded).
        assert paths == {"docs/a.md"}


# ---------------------------------------------------------------------------
# Audit → is_active flip
# ---------------------------------------------------------------------------

class TestAuditDeactivation:
    def test_delete_action_flips_is_active(self, seeded_conn):
        before = seeded_conn.execute(
            "SELECT is_active FROM document_chunks WHERE source_path = ?",
            ("docs/a.md",),
        ).fetchone()[0]
        assert before == 1

        out = audit_log_record(
            seeded_conn, doc_path="docs/a.md", action="deleted",
            reason="superseded by Phase O",
        )
        assert out["chunks_deactivated"] == 1

        after = seeded_conn.execute(
            "SELECT is_active FROM document_chunks WHERE source_path = ?",
            ("docs/a.md",),
        ).fetchone()[0]
        assert after == 0

    def test_revert_action_flips_is_active(self, seeded_conn):
        out = audit_log_record(
            seeded_conn, doc_path="docs/a.md", action="reverted",
            reason="rolled back to prior version",
        )
        assert out["chunks_deactivated"] == 1

    def test_update_action_does_not_flip(self, seeded_conn):
        out = audit_log_record(
            seeded_conn, doc_path="docs/a.md", action="updated",
            reason="minor tweak",
        )
        assert out["chunks_deactivated"] == 0
        active = seeded_conn.execute(
            "SELECT is_active FROM document_chunks WHERE source_path = ?",
            ("docs/a.md",),
        ).fetchone()[0]
        assert active == 1

    def test_deactivation_propagates_to_search(self, seeded_conn):
        audit_log_record(
            seeded_conn, doc_path="docs/a.md", action="deleted",
            reason="test",
        )
        results = doc_search(seeded_conn, "audit log", limit=10, mode="lexical")
        paths = {r["source_path"] for r in results}
        assert "docs/a.md" not in paths


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

class TestFrontmatterParser:
    def test_parses_required_fields(self):
        text = (
            "<!-- domain:OPS | layer:reference | ssot:true | updated:2026-04-28 -->\n"
            "# Title\n\nBody"
        )
        fm = _parse_front_matter(text)
        assert fm["domain"] == "OPS"
        assert fm["layer"] == "reference"
        assert fm["ssot"] == "true"
        assert fm["updated_iso"] == "2026-04-28"

    def test_tolerates_extra_keys(self):
        text = (
            "<!-- domain:OPS | layer:reference | ssot:ref | "
            "source:outcome_history#42 | updated:2026-04-28 -->\nBody"
        )
        fm = _parse_front_matter(text)
        assert fm["domain"] == "OPS"
        assert fm["source"] == "outcome_history#42"
        assert fm["updated_iso"] == "2026-04-28"

    def test_missing_frontmatter_returns_empty(self):
        fm = _parse_front_matter("# Just a heading\nNo frontmatter")
        assert fm == {}


# ---------------------------------------------------------------------------
# Query-time hint extraction
# ---------------------------------------------------------------------------

class TestSuggestFiltersFromQuery:
    def test_empty_query_returns_empty(self):
        assert _suggest_filters_from_query("") == {}

    def test_domain_keyword_match(self):
        h = _suggest_filters_from_query("how does backend auth work")
        assert h["suggested_domain"] == "BACKEND"

    def test_layer_runbook_keyword(self):
        h = _suggest_filters_from_query("runbook for incident response")
        assert h["suggested_layer"] == "runbook"
        assert h["suggested_domain"] == "OPS"

    def test_recency_phrase_recent(self):
        h = _suggest_filters_from_query("recent ADR for deployment")
        assert h["suggested_layer"] == "adr"
        # "recent" → 90-day cutoff, ISO date format
        assert "suggested_since_iso" in h
        assert len(h["suggested_since_iso"]) == 10

    def test_explicit_since_year(self):
        h = _suggest_filters_from_query("frontend changes since 2026")
        assert h["suggested_domain"] == "FRONTEND"
        assert h["suggested_since_iso"] == "2026-01-01"

    def test_explicit_since_year_month(self):
        h = _suggest_filters_from_query("after 2026-04 the schema changed")
        assert h["suggested_since_iso"] == "2026-04-01"

    def test_unrelated_query_no_hints(self):
        h = _suggest_filters_from_query("what is foo bar baz quux")
        assert h == {}


# ---------------------------------------------------------------------------
# Active-task context (env-var driven)
# ---------------------------------------------------------------------------

class TestActiveTaskContext:
    def test_no_env_returns_empty(self, monkeypatch):
        monkeypatch.delenv("COS_AGENT_DIR", raising=False)
        assert _active_task_context() == {}

    def test_swimlane_maps_to_domain(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        (tmp_path / ".swimlane").write_text("backend\n", encoding="utf-8")
        assert _active_task_context() == {"domain": "BACKEND"}

    def test_unknown_swimlane_skipped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        (tmp_path / ".swimlane").write_text("nonsense\n", encoding="utf-8")
        assert _active_task_context() == {}

    def test_missing_swimlane_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        # No .swimlane file written
        assert _active_task_context() == {}


# ---------------------------------------------------------------------------
# doc_search auto_context + return_meta integration
# ---------------------------------------------------------------------------

class TestAutoContextAndReturnMeta:
    def test_return_meta_shape(self, seeded_conn):
        results, meta = doc_search(
            seeded_conn, "audit log", limit=5, mode="lexical",
            return_meta=True,
        )
        assert isinstance(results, list)
        assert "filter_hints" in meta
        assert "applied" in meta

    def test_filter_hints_from_query(self, seeded_conn):
        _, meta = doc_search(
            seeded_conn, "recent backend audit log", mode="lexical",
            return_meta=True,
        )
        assert meta["filter_hints"]["suggested_domain"] == "BACKEND"
        assert "suggested_since_iso" in meta["filter_hints"]

    def test_auto_context_applies_swimlane(self, seeded_conn, monkeypatch, tmp_path):
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        (tmp_path / ".swimlane").write_text("backend\n", encoding="utf-8")
        results, meta = doc_search(
            seeded_conn, "audit log", mode="lexical",
            auto_context=True, return_meta=True,
        )
        assert meta["applied"].get("domain") == "BACKEND"

    def test_explicit_domain_beats_auto_context(self, seeded_conn, monkeypatch, tmp_path):
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        (tmp_path / ".swimlane").write_text("backend\n", encoding="utf-8")
        _, meta = doc_search(
            seeded_conn, "audit log", mode="lexical",
            domain="OPS", auto_context=True, return_meta=True,
        )
        # Explicit OPS wins over inferred BACKEND.
        assert meta["applied"]["domain"] == "OPS"

    def test_auto_context_off_by_default(self, seeded_conn, monkeypatch, tmp_path):
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        (tmp_path / ".swimlane").write_text("backend\n", encoding="utf-8")
        _, meta = doc_search(
            seeded_conn, "audit log", mode="lexical", return_meta=True,
        )
        # No auto_context → swimlane ignored.
        assert "domain" not in meta["applied"]

    def test_return_meta_false_returns_list(self, seeded_conn):
        results = doc_search(seeded_conn, "audit log", mode="lexical")
        # Backwards-compat: legacy callers get plain list.
        assert isinstance(results, list)
