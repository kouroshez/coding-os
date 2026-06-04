"""Tests for graph_os.extractors.task_deps (I.3).

Ship gate (Section 19 I.3):
  - backfill test
  - incremental test
  - 50k-task benchmark — enforced in I.13, smoke here only
"""

from __future__ import annotations

import pytest

from graph_os.extractors import task_deps

TASK_042 = """\
<!-- domain:BACKEND | layer:task | ssot:true -->
# TASK-042: [BACKEND] Example commission model

Purpose: demonstrate a task with dependencies.

## Goal

Build a commission model that pays 15% to agents.

## Read First

- docs/engineering/backend-rules.md
- docs/playbooks/backend-api.md

## Source of Truth

- docs/architecture.md
- docs/api-contracts/error-format.md

## Scope
### In
- models/commission.py
### Out
- frontend changes

## Requirements

- Transactional writes
- Idempotent endpoint

## Dependencies

- TASK-199
- TASK-007

## Verification

- make verify
"""


# ---------------------------------------------------------------------------
# Canonical ids + uid shape
# ---------------------------------------------------------------------------


class TestCanonicalIds:
    def test_task_uid_zero_padded(self):
        assert task_deps.task_uid("TASK-7") == "task:file:TASK-007"
        assert task_deps.task_uid("TASK-042") == "task:file:TASK-042"
        assert task_deps.task_uid("TASK-1024") == "task:file:TASK-1024"

    def test_task_uid_trims_noise(self):
        assert task_deps.task_uid("See TASK-9 for details") == "task:file:TASK-009"

    def test_task_uid_unknown_input_preserved(self):
        # Falls through when no TASK- prefix so callers can distinguish.
        assert task_deps.task_uid("unknown").startswith("task:file:")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


class TestExtract:
    def _extract(self, content: str = TASK_042, path: str = "docs/tasks/TASK-042-example.md"):
        return task_deps.extract(path, content)

    def test_emits_task_file_node(self):
        r = self._extract()
        # task_deps emits the canonical TASK-042 node and md_links'
        # _promote_stubs synthesises stubs for any other TASK-XXX uids
        # the file references (e.g., depends_on TASK-007 / TASK-199).
        # We assert the canonical one is present and a singleton among
        # non-stub task_file nodes.
        non_stub = [n for n in r.nodes if n.kind == "task:file" and not n.metadata.get("stub")]
        assert len(non_stub) == 1
        assert non_stub[0].uid == "task:file:TASK-042"
        assert "BACKEND" in (non_stub[0].label or "")

    def test_metadata_includes_domain(self):
        r = self._extract()
        task = next(n for n in r.nodes if n.kind == "task:file" and not n.metadata.get("stub"))
        assert task.metadata.get("domain") == "BACKEND"
        assert task.metadata.get("task_id") == "TASK-042"

    def test_depends_on_edges(self):
        r = self._extract()
        dep_edges = [e for e in r.edges if e.edge_type == "depends_on"]
        targets = {e.target_uid for e in dep_edges}
        assert "task:file:TASK-199" in targets
        assert "task:file:TASK-007" in targets
        assert len(dep_edges) == 2

    def test_blocks_edges_are_inverse(self):
        r = self._extract()
        blocks = [e for e in r.edges if e.edge_type == "blocks"]
        assert len(blocks) == 2
        # Inverse of depends_on.
        assert {e.source_uid for e in blocks} == {
            "task:file:TASK-199",
            "task:file:TASK-007",
        }

    def test_references_doc_from_source_of_truth(self):
        r = self._extract()
        ref_edges = [e for e in r.edges if e.edge_type == "references_doc"]
        targets = {e.target_uid for e in ref_edges}
        assert "doc:file:docs/architecture.md" in targets
        assert "doc:file:docs/api-contracts/error-format.md" in targets

    def test_references_doc_from_read_first(self):
        r = self._extract()
        ref_edges = [e for e in r.edges if e.edge_type == "references_doc"]
        targets = {e.target_uid for e in ref_edges}
        assert "doc:file:docs/engineering/backend-rules.md" in targets
        assert "doc:file:docs/playbooks/backend-api.md" in targets

    def test_source_of_truth_higher_confidence_than_read_first(self):
        r = self._extract()
        sot_edges = [
            e
            for e in r.edges
            if e.edge_type == "references_doc" and "source_of_truth" in (e.source_span or "")
        ]
        rf_edges = [
            e
            for e in r.edges
            if e.edge_type == "references_doc" and "read_first" in (e.source_span or "")
        ]
        assert all(e.confidence >= 0.95 for e in sot_edges)
        assert all(e.confidence <= 0.95 for e in rf_edges)

    def test_stub_nodes_for_referenced_docs(self):
        """Edges to other files must not dangle — stubs are promoted."""
        r = self._extract()
        uids = {n.uid for n in r.nodes}
        assert "doc:file:docs/architecture.md" in uids
        assert "task:file:TASK-199" in uids

    def test_not_a_task_falls_back_gracefully(self):
        r = task_deps.extract("docs/random.md", "# Not a task\n\nSome body")
        assert r.parse_errors
        assert r.parse_errors[0].kind == "not_a_task"
        # Still emits *some* node so the graph keeps the file visible.
        assert any(n.kind == "task:file" for n in r.nodes)

    def test_self_dependency_flagged(self):
        content = TASK_042.replace("TASK-199", "TASK-042").replace("TASK-007", "TASK-042")
        r = self._extract(content=content)
        errors = [e for e in r.parse_errors if e.kind == "self_dependency"]
        assert errors
        # No depends_on edges emitted for self.
        depends = [e for e in r.edges if e.edge_type == "depends_on"]
        assert len(depends) == 0

    def test_deterministic_round_trip(self):
        first = self._extract()
        second = self._extract()
        assert [n.uid for n in first.nodes] == [n.uid for n in second.nodes]
        assert [(e.source_uid, e.target_uid, e.edge_type) for e in first.edges] == [
            (e.source_uid, e.target_uid, e.edge_type) for e in second.edges
        ]

    def test_backend_round_trip(self, migrated_conn):
        """Upsert all nodes + edges via SqliteBackend — no dangling uids."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        r = self._extract()
        n_written, e_written = backend.bulk_upsert(r.nodes, r.edges)
        assert n_written == len(r.nodes)
        assert e_written == len(r.edges)

    def test_fatal_exception_is_contained(self, monkeypatch):
        """A crash in task_parser must not propagate."""

        def boom(_content):
            raise RuntimeError("boom")

        # Replace the imported module's parser after first load.
        parser = task_deps._import_task_parser()
        monkeypatch.setattr(parser, "parse_task_file", boom)
        r = task_deps.extract("docs/tasks/TASK-042-x.md", TASK_042)
        assert any(p.kind == "fatal" for p in r.parse_errors)


# ---------------------------------------------------------------------------
# produces_code_edges
# ---------------------------------------------------------------------------


class TestProducesCode:
    def test_emits_one_edge_per_unique_file(self):
        edges = task_deps.produces_code_edges(
            task_id="TASK-42",
            modified_files=["core/foo.py", "core/foo.py", "tests/test_foo.py"],
        )
        assert len(edges) == 2
        targets = {e.target_uid for e in edges}
        assert targets == {
            "code:file:core/foo.py",
            "code:file:tests/test_foo.py",
        }

    def test_markdown_target_routes_to_doc_uid(self):
        edges = task_deps.produces_code_edges(
            task_id="TASK-42",
            modified_files=["docs/guide.md"],
        )
        assert edges[0].target_uid == "doc:file:docs/guide.md"

    def test_normalises_backslashes(self):
        edges = task_deps.produces_code_edges(
            task_id="TASK-42",
            modified_files=["core\\foo.py"],
        )
        assert edges[0].target_uid == "code:file:core/foo.py"

    def test_confidence_below_manual_edges(self):
        edges = task_deps.produces_code_edges(task_id="TASK-42", modified_files=["a.py"])
        assert edges[0].confidence == pytest.approx(0.85)

    def test_canonicalises_task_id(self):
        edges = task_deps.produces_code_edges(
            task_id="TASK-7",
            modified_files=["a.py"],
        )
        assert edges[0].source_uid == "task:file:TASK-007"

    def test_empty_input_no_edges(self):
        assert task_deps.produces_code_edges(task_id="TASK-1", modified_files=[]) == []


# ---------------------------------------------------------------------------
# Doc-path resolution helpers
# ---------------------------------------------------------------------------


class TestResolveDocRef:
    def test_plain_path_normalised(self):
        assert task_deps._resolve_doc_ref("docs/tasks/T.md", "docs/spec.md") == "docs/spec.md"

    def test_relative_parent_resolves_against_origin_dir(self):
        assert (
            task_deps._resolve_doc_ref("docs/tasks/T.md", "../engineering/x.md")
            == "docs/engineering/x.md"
        )

    def test_dot_slash_relative(self):
        assert (
            task_deps._resolve_doc_ref("docs/tasks/T.md", "./sibling.md") == "docs/tasks/sibling.md"
        )

    def test_escapes_repo_root_returns_none(self):
        assert task_deps._resolve_doc_ref("docs/T.md", "../../../etc/passwd") is None

    def test_backtick_ref_returns_none(self):
        assert task_deps._resolve_doc_ref("docs/T.md", "some`code`ref") is None

    def test_whitespace_ref_returns_none(self):
        assert task_deps._resolve_doc_ref("docs/T.md", "a b.md") is None

    def test_empty_ref_returns_none(self):
        assert task_deps._resolve_doc_ref("docs/T.md", "   ") is None


class TestExtractDocPaths:
    def test_pulls_and_dedups_md_paths(self):
        out = task_deps._extract_doc_paths(
            ["see docs/a.md and docs/b.md", "docs/a.md again"],
            origin_path="docs/tasks/T.md",
        )
        assert out == ["docs/a.md", "docs/b.md"]

    def test_drops_root_escaping_ref(self):
        out = task_deps._extract_doc_paths(["../../../../outside.md"], origin_path="docs/T.md")
        assert out == []


class TestExtractScopePaths:
    def test_pulls_code_paths_and_dedups(self):
        out = task_deps._extract_scope_paths(["edit src/a.py and src/a.py"])
        assert out == ["src/a.py"]

    def test_multiple_languages(self):
        out = task_deps._extract_scope_paths(["touch lib/x.ts and pkg/y.go"])
        assert set(out) == {"lib/x.ts", "pkg/y.go"}
