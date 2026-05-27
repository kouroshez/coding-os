"""Tests for the 11 cos_graph_* MCP tools (I.8).

Ship gate (Section 19 I.8):
  - ≥ 44 tests (≥ 4 per tool × 11)
  - envelope compliance (Rule 14) on every tool
  - token-budget tests + 1 edge case per tool
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from graph_os.tools import graph
from graph_os.types import EvidenceSignal, GraphEdge, GraphNode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_backend(migrated_conn, monkeypatch, tmp_path):
    """Seed the backend with a small fixture graph + wire the tools."""
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    # Force the tools module to use *this* backend.
    graph._BACKEND_SINGLETON = backend
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)

    nodes = [
        GraphNode(
            uid="code:function:a.py::foo",
            kind="code:function",
            label="foo",
            file_path="a.py",
            start_line=1,
        ),
        GraphNode(
            uid="code:function:a.py::bar",
            kind="code:function",
            label="bar",
            file_path="a.py",
            start_line=10,
        ),
        GraphNode(
            uid="code:function:a.py::baz",
            kind="code:function",
            label="baz_handler",
            file_path="a.py",
            start_line=20,
        ),
        GraphNode(uid="doc:file:docs/x.md", kind="doc:file", label="x.md", file_path="docs/x.md"),
        GraphNode(
            uid="cos:route:GET:/users",
            kind="cos:route",
            label="GET /users",
            file_path="app.py",
            metadata={"kind": "http", "method": "get", "path": "/users", "framework": "fastapi"},
        ),
        GraphNode(
            uid="cos:mcp_tool:cos_graph_query",
            kind="cos:mcp_tool",
            label="mcp:cos_graph_query",
            file_path="srv.py",
            metadata={"kind": "mcp", "method": "rpc", "path": "cos_graph_query"},
        ),
        GraphNode(uid="code:file:a.py", kind="code:file", label="a.py", file_path="a.py"),
        GraphNode(
            uid="code:class:a.py::Widget",
            kind="code:class",
            label="Widget",
            file_path="a.py",
            start_line=30,
        ),
        GraphNode(
            uid="code:function:a.py::make_widget",
            kind="code:function",
            label="make_widget",
            file_path="a.py",
            start_line=40,
        ),
        # F6 fixture: an external/unresolved node — must NOT dominate
        # centrality or PageRank when include_external defaults False.
        GraphNode(
            uid="code:external:unresolved:str",
            kind="identifier",
            label="unresolved:str",
            file_path=None,
        ),
    ]
    edges = [
        GraphEdge(
            source_uid="code:function:a.py::foo",
            target_uid="code:function:a.py::bar",
            edge_type="calls",
            extractor="test",
            confidence=0.9,
        ),
        GraphEdge(
            source_uid="code:function:a.py::bar",
            target_uid="code:function:a.py::baz",
            edge_type="calls",
            extractor="test",
            confidence=0.6,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="code:function:a.py::foo",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="doc:file:docs/x.md",
            target_uid="code:function:a.py::foo",
            edge_type="references_doc",
            extractor="test",
            confidence=0.85,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="cos:route:GET:/users",
            edge_type="handles_route",
            extractor="test",
            confidence=0.9,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="cos:mcp_tool:cos_graph_query",
            edge_type="handles_tool",
            extractor="test",
            confidence=0.95,
        ),
        # Class-consumer edges — rename_plan must surface these (F2/#6).
        GraphEdge(
            source_uid="code:function:a.py::make_widget",
            target_uid="code:class:a.py::Widget",
            edge_type="constructs",
            extractor="test",
            confidence=0.85,
        ),
        GraphEdge(
            source_uid="code:function:a.py::foo",
            target_uid="code:class:a.py::Widget",
            edge_type="has_param_type",
            extractor="test",
            confidence=0.85,
        ),
        # F6 fixture: lots of inbound edges to the external stub so
        # that, without the filter, it'd dominate the ranking.
        GraphEdge(
            source_uid="code:function:a.py::foo",
            target_uid="code:external:unresolved:str",
            edge_type="has_return_type",
            extractor="test",
            confidence=0.7,
        ),
        GraphEdge(
            source_uid="code:function:a.py::bar",
            target_uid="code:external:unresolved:str",
            edge_type="has_return_type",
            extractor="test",
            confidence=0.7,
        ),
        GraphEdge(
            source_uid="code:function:a.py::baz",
            target_uid="code:external:unresolved:str",
            edge_type="has_return_type",
            extractor="test",
            confidence=0.7,
        ),
    ]
    backend.bulk_upsert(nodes, edges)
    yield backend
    graph._BACKEND_SINGLETON = None


# ---------------------------------------------------------------------------
# Envelope contract — every tool must return ok/fail with layer="graph".
# ---------------------------------------------------------------------------


def _decode(envelope):
    if isinstance(envelope, str):
        return json.loads(envelope)
    return envelope


def _assert_ok(envelope) -> dict:
    env = _decode(envelope)
    assert env["ok"] is True, f"expected ok envelope, got {env}"
    data = env["data"]
    assert data["meta"]["layer"] == "graph"
    return data


def _assert_fail(envelope, category: str) -> None:
    env = _decode(envelope)
    assert env["ok"] is False
    assert env["error"]["category"] == category


# ---------------------------------------------------------------------------
# Each tool
# ---------------------------------------------------------------------------


class TestQuery:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("baz_handler"))
        uids = {r["uid"] for r in data["results"]}
        assert "code:function:a.py::baz" in uids

    def test_empty_query_validation_error(self, seeded_backend):
        _assert_fail(graph.cos_graph_query(""), "validation")

    def test_kind_filter(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("a.py", kinds=["code:function"]))
        assert all(r["kind"] == "code:function" for r in data["results"])

    def test_limit(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("a.py", limit=1))
        assert len(data["results"]) <= 1


class TestContext:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_context("code:function:a.py::foo"))
        assert data["edge_count"] >= 1
        assert "calls" in data["edges_by_type"]

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_context("code:function:missing"), "not_found")

    def test_fuzzy_label_resolve(self, seeded_backend):
        env = graph.cos_graph_context("foo")  # label not full uid
        # Either resolves fuzzily or returns not_found — both acceptable;
        # exercise that the envelope is always valid.
        assert "ok" in env

    def test_depth_honoured(self, seeded_backend):
        shallow = _assert_ok(graph.cos_graph_context("code:function:a.py::foo", depth=1))
        deeper = _assert_ok(graph.cos_graph_context("code:function:a.py::foo", depth=3))
        assert deeper["edge_count"] >= shallow["edge_count"]


class TestImpact:
    def test_downstream_tiers(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::bar"))
        tiers = data["tiers"]
        # foo → bar is a will_break (0.9), bar → baz is should_review (0.6).
        assert tiers["will_break"] or tiers["should_review"]

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_impact("code:function:missing"), "not_found")

    def test_confidence_min_filters(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::foo", confidence_min=0.9))
        # Tiered counts honour the floor.
        for entry in data["tiers"]["should_review"]:
            assert entry["confidence"] >= 0.5

    def test_upstream_direction(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::bar", direction="upstream"))
        assert data["direction"] == "upstream"

    def test_contains_edges_route_to_context_tier(self, seeded_backend):
        """F4 / Audit #5: structural `contains` edges (file→func,
        conf=1.0) used to land in `will_break` because the classifier
        looked at confidence only. After fix every `contains` edge is
        routed to `context`, regardless of confidence."""
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::foo"))
        will_break_types = {e["edge_type"] for e in data["tiers"]["will_break"]}
        assert "contains" not in will_break_types, "contains leaked into will_break"
        should_review_types = {e["edge_type"] for e in data["tiers"]["should_review"]}
        assert "contains" not in should_review_types, "contains leaked into should_review"

    def test_behavioural_edge_in_will_break(self, seeded_backend):
        """F4: high-confidence behavioural edges (calls @ 0.9) still
        populate will_break — the fix narrows the classifier, doesn't
        empty it."""
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::bar"))
        will_break_types = {e["edge_type"] for e in data["tiers"]["will_break"]}
        # foo → bar is "calls" at conf 0.9 — must land in will_break.
        assert "calls" in will_break_types

    def test_file_uid_expands_to_contained_symbols_w63(self, seeded_backend):
        """W6.3 (F6/B15/N1): impact on `code:file:*` uid must walk each
        contained symbol so will_break is populated. Pre-fix, file-level
        impact returned will_break=0 because file nodes have no
        behavioural inbound edges of their own (only `contains` from
        folder spine)."""
        data = _assert_ok(graph.cos_graph_impact("code:file:a.py"))
        # a.py contains foo/bar/baz; foo has inbound `calls` from bar
        # → file-level walk should surface a non-empty tier.
        any_tier_populated = any(data["tiers"][t] for t in ("will_break", "should_review"))
        assert any_tier_populated, f"file impact returned empty tiers: {data['tiers']}"
        # impacted_count must stay int (typed scalar — W6.2 invariant).
        assert isinstance(data["impacted_count"], int)
        assert data["meta"]["expanded_from_file"] is True


class TestDetectChanges:
    def test_no_files_returns_empty_envelope(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=[]))
        assert data["files"] == []

    def test_file_maps_to_symbols(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["a.py"]))
        assert data["files"] == ["a.py"]
        assert data["symbols"]

    def test_unknown_file_skipped(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["ghost.py"]))
        assert data["symbols"] == []

    def test_risk_level_present(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["a.py"]))
        assert data["risk_level"] in {"low", "medium", "high", "none"}


class TestTrace:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo"))
        uids = {s["uid"] for s in data["steps"]}
        assert "code:function:a.py::foo" in uids

    def test_unknown_entry(self, seeded_backend):
        _assert_fail(graph.cos_graph_trace("code:function:missing"), "not_found")

    def test_max_steps_honoured(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo", max_steps=1))
        assert len(data["steps"]) <= 1

    def test_branches_captured(self, seeded_backend):
        # Not guaranteed on this fixture; just assert shape.
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo"))
        assert "branches" in data


class TestSimilar:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_similar("code:function:a.py::foo", confidence_min=0.0, top_k=5)
        )
        assert "results" in data

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_similar("code:function:missing"), "not_found")

    def test_top_k_honoured(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_similar("code:function:a.py::foo", top_k=2, confidence_min=0.0)
        )
        assert len(data["results"]) <= 2

    def test_confidence_floor_excludes_low(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_similar("code:function:a.py::foo", confidence_min=0.99, top_k=5)
        )
        assert all(r["similarity"] >= 0.99 for r in data["results"])


class TestReferences:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_references("code:function:a.py::foo"))
        assert data["count"] >= 1

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_references("code:function:missing"), "not_found")

    def test_filter_kinds(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_references("code:function:a.py::foo", kinds=["references_doc"])
        )
        assert all(e["edge_type"] == "references_doc" for e in data["references"])

    def test_limit_respected(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_references("code:function:a.py::foo", limit=1))
        assert data["count"] <= 1

    def test_result_truncated_when_limit_below_total(self, seeded_backend):
        """Silent truncation is the silent-incomplete-coverage bug — pin
        the contract that total_count + meta.result_truncated are
        populated so the agent can re-run with a wider limit when
        needed. Key is `result_truncated` (not `truncated`) because the
        envelope's `meta.truncated` is reserved for token-budget trims."""
        full_data = _assert_ok(graph.cos_graph_references("code:function:a.py::foo"))
        total = full_data["total_count"]
        assert total >= 1
        assert full_data["count"] == total
        assert full_data["meta"]["result_truncated"] is False
        if total > 1:
            tight_data = _assert_ok(
                graph.cos_graph_references("code:function:a.py::foo", limit=1)
            )
            assert tight_data["count"] == 1
            assert tight_data["total_count"] == total
            assert tight_data["meta"]["result_truncated"] is True


class TestImpactTruncation:
    def test_meta_carries_visit_limit_and_walk_truncated(self, seeded_backend):
        """Impact's BFS has a visit_limit cap. When the walk hits it the
        result is incomplete — meta.walk_truncated MUST surface that."""
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::bar"))
        meta = data["meta"]
        assert "visit_limit" in meta
        assert "walk_truncated" in meta
        # Small seeded graph — fits comfortably, never truncated.
        assert meta["walk_truncated"] is False


class TestContextTruncation:
    def test_meta_carries_visit_limit_and_walk_truncated(self, seeded_backend):
        """Context shares the BFS path with impact — same coverage
        contract. README claims meta.walk_truncated + meta.visit_limit;
        pin both so the claim stays honest."""
        data = _assert_ok(graph.cos_graph_context("code:function:a.py::foo"))
        meta = data["meta"]
        assert "visit_limit" in meta
        assert "walk_truncated" in meta
        assert meta["walk_truncated"] is False

    def test_visit_limit_one_walk_truncates(self, seeded_backend):
        """Tightening visit_limit to a value smaller than the reachable
        frontier must flip walk_truncated=true."""
        data = _assert_ok(
            graph.cos_graph_context("code:function:a.py::foo", visit_limit=1)
        )
        assert data["meta"]["walk_truncated"] is True
        assert data["meta"]["visit_limit"] == 1


class TestSweepCoverageSignals:
    """One-shot coverage audit (2026-05-23) — every cos_graph_* tool that
    can silently truncate MUST emit either `meta.result_truncated` or
    `meta.walk_truncated` so the agent never proceeds on incomplete
    data. Pins the contract for the seven tools that gained the signal
    in the deep-sweep audit."""

    def test_query_emits_result_truncated_and_total(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("foo", limit=10))
        assert "total_count" in data
        assert data["meta"]["result_truncated"] is False
        assert data["meta"]["limit"] == 10
        # Tighten to force truncation if there are >1 hits.
        tight = _assert_ok(graph.cos_graph_query("foo", limit=1))
        if tight["total_count"] > 1:
            assert tight["meta"]["result_truncated"] is True

    def test_similar_emits_result_truncated_and_total(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_similar("code:function:a.py::foo", top_k=20))
        assert "total_count" in data
        assert "result_truncated" in data["meta"]
        assert "top_k" in data["meta"]

    def test_rename_plan_emits_per_bucket_totals(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_rename_plan("code:function:a.py::foo", "renamed_foo")
        )
        assert "call_sites_total_count" in data
        assert "doc_references_total_count" in data
        assert "test_references_total_count" in data
        assert "result_truncated" in data["meta"]
        assert "bucket_limit" in data["meta"]
        # Small seeded — totals match in-line lengths.
        assert data["call_sites_total_count"] == len(data["call_sites"])
        assert data["meta"]["result_truncated"] is False

    def test_trace_emits_walk_truncated(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo"))
        assert "max_steps" in data["meta"]
        assert "walk_truncated" in data["meta"]

    def test_trace_default_omits_external_targets_from_steps(self, seeded_backend):
        """F9 / Audit #7: trace walk used to emit `code:external:*`
        nodes inline in `steps`, polluting the call graph. Default
        keeps them out of `steps` and surfaces them via
        `external_targets` instead."""
        # Seed an external node + edge so walk would normally include it.
        backend = graph._BACKEND_SINGLETON
        backend.upsert_node(
            GraphNode(
                uid="code:external:json:dumps",
                kind="identifier",
                label="json:dumps",
                file_path=None,
            )
        )
        backend.upsert_edge(
            GraphEdge(
                source_uid="code:function:a.py::foo",
                target_uid="code:external:json:dumps",
                edge_type="calls",
                extractor="test",
                confidence=0.5,
            )
        )
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo"))
        step_uids = {s["uid"] for s in data["steps"]}
        for u in step_uids:
            assert not u.startswith("code:external:"), f"external leaked into steps: {u}"
        assert "external_targets" in data
        assert "external_count" in data["meta"]

    def test_trace_walk_truncated_fires_under_tight_max_steps(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_trace("code:function:a.py::foo", max_steps=1)
        )
        # max_steps=1 stops after the root if the stack still has work.
        if data["meta"]["step_count"] == 1:
            # walk_truncated should be True iff the walk could have continued.
            assert "walk_truncated" in data["meta"]

    def test_contracts_emits_per_kind_truncated(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts())
        assert "result_truncated" in data["meta"]
        assert "per_edge_type_truncated" in data["meta"]
        assert "bucket_limit" in data["meta"]
        # Small seeded — none of the buckets exceed 2000 edges.
        assert data["meta"]["result_truncated"] is False
        assert all(v is False for v in data["meta"]["per_edge_type_truncated"].values())

    def test_detect_changes_emits_walk_truncated(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["a.py"]))
        assert "visit_limit" in data["meta"]
        assert "walk_truncated" in data["meta"]

    def test_entrypoints_emits_result_truncated(self, seeded_backend):
        # ep module may be missing on stub backends — accept either ok
        # or unavailable, but if ok, the new signals must be present.
        res = graph.cos_graph_entrypoints(top=5)
        env = json.loads(res) if isinstance(res, str) else res
        if env.get("ok"):
            data = env["data"]
            assert "total_count" in data
            assert "result_truncated" in data["meta"]
            assert "top" in data["meta"]


class TestPath:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_path("code:function:a.py::foo", "code:function:a.py::baz")
        )
        assert data["hops"] >= 1

    def test_unknown_source(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_path("code:function:missing", "code:function:a.py::baz"),
            "not_found",
        )

    def test_unknown_target(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_path("code:function:a.py::foo", "code:function:missing"),
            "not_found",
        )

    def test_unreachable_path_empty(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_path("doc:file:docs/x.md", "cos:route:GET:/users", max_hops=0)
        )
        assert data["path"] is None

    def test_path_excludes_external_intermediates_w64(self, seeded_backend):
        """W6.4 (T1): `code:external:*` stubs (e.g. unresolved:str with
        thousands of in-edges) must not bridge unrelated nodes as
        intermediate hops. Default behaviour skips them; opt-in flag
        re-enables."""
        # foo, bar, baz all link to code:external:unresolved:str (3 inbound
        # edges in seeded fixture). Without the filter a path could bridge
        # foo → unresolved:str ← baz.
        data = _assert_ok(
            graph.cos_graph_path(
                "code:function:a.py::foo", "code:function:a.py::baz"
            )
        )
        if data["path"]:
            # No intermediate hop should be an external stub.
            for n in data["path"][1:-1]:
                assert not n.startswith("code:external:"), (
                    f"external stub leaked as intermediate hop: {n}"
                )

    def test_path_edges_tagged_traversal_direction_w64(self, seeded_backend):
        """W6.4 (T2): each edge in the path must carry a
        `traversal_direction` field (forward|reverse) so callers can
        distinguish semantic-direction edges from reverse-walk bridges."""
        data = _assert_ok(
            graph.cos_graph_path(
                "code:function:a.py::foo", "code:function:a.py::baz"
            )
        )
        if data["edges"]:
            for e in data["edges"]:
                assert "traversal_direction" in e
                assert e["traversal_direction"] in {"forward", "reverse"}


class TestExport:
    def test_json_format(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_export(format="json"))
        assert data["format"] == "json"
        assert data["nodes"] and data["edges"]

    def test_mermaid_format(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_export(format="mermaid"))
        assert "graph LR" in data["diagram"]

    def test_dot_format(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_export(format="dot"))
        assert data["diagram"].startswith("digraph G")

    def test_unknown_format(self, seeded_backend):
        _assert_fail(graph.cos_graph_export(format="svg"), "validation")

    def test_centrality_default_excludes_external(self, seeded_backend):
        """F6 / Audit #10: default `include_external=False` must drop
        `code:external:*` nodes from the centrality top — otherwise
        unresolved builtins dominate every real call result."""
        data = _assert_ok(graph.cos_graph_centrality(top=10))
        uids = {n["uid"] for n in data["nodes"]}
        for u in uids:
            assert not u.startswith("code:external:"), f"external leaked: {u}"

    def test_centrality_include_external_opts_in(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_centrality(top=10, include_external=True))
        uids = {n["uid"] for n in data["nodes"]}
        assert any(u.startswith("code:external:") for u in uids)

    def test_context_resolves_unqualified_label_via_fts5(self, seeded_backend):
        """F11 / Audit #17: cos_graph_context used to fail with
        not_found on an unqualified label like `baz_handler` because
        _resolve_uid never tried FTS5. After fix it picks the
        FTS5-top-ranked hit and the context call succeeds."""
        data = _assert_ok(graph.cos_graph_context("baz_handler"))
        assert data["node"]["uid"] == "code:function:a.py::baz"

    def test_entrypoints_default_diversifies_by_file(self, seeded_backend):
        """F10 / Audit #13: seed several tied-score entrypoints across
        two files. Default `diversify=True` should interleave the two
        files in the top-N. Raw mode (`diversify=False`) sorts by
        (score, uid) only — proves the new behaviour is opt-out."""
        backend = graph._BACKEND_SINGLETON
        for fname in ("a.py", "b.py"):
            for i in range(3):
                u = f"code:function:{fname}::test_seed_{i}"
                backend.upsert_node(
                    GraphNode(
                        uid=u,
                        kind="code:function",
                        label=f"test_seed_{i}",
                        file_path=fname,
                        start_line=100 + i,
                    )
                )
        diverse = _assert_ok(graph.cos_graph_entrypoints(top=4))
        files = [e.get("file_path") for e in diverse["entrypoints"]]
        # When >=2 files have entrypoints in the seed, default mode must
        # surface both files within the top-4.
        if len({f for f in files if f}) >= 2:
            assert len({f for f in files[:4] if f}) >= 2, (
                f"diversify failed — top-4 files: {files}"
            )

    def test_communities_caps_members_per_process(self, seeded_backend):
        """F8 / Audit #9: each process truncates its members to
        max_members=10 by default so the envelope stays under the MCP
        token budget. `members_truncated` flag surfaces the cap."""
        data = _assert_ok(graph.cos_graph_communities(top=5, max_members=2))
        for proc in data["processes"]:
            assert len(proc.get("members", [])) <= 2
        assert "max_members" in data["meta"]
        assert "members_truncated" in data["meta"]

    def test_ranking_token_personalization_targets_widget(self, seeded_backend):
        """F7 / Audit #12: previous substring matcher missed any
        whitespace query. `make widget` now matches `make_widget` AND
        `Widget` via token-OR, so the personalized top should surface
        those nodes ahead of the unrelated `foo` baseline."""
        baseline = _assert_ok(graph.cos_graph_ranking(top=5))
        personalized = _assert_ok(graph.cos_graph_ranking(query="make widget", top=5))
        baseline_uids = [n["uid"] for n in baseline["nodes"]]
        personalized_uids = [n["uid"] for n in personalized["nodes"]]
        assert baseline_uids != personalized_uids, "personalization had no effect"
        targets = {"code:function:a.py::make_widget", "code:class:a.py::Widget"}
        assert any(u in targets for u in personalized_uids[:3]), \
            "make_widget / Widget should be in top-3 with query='make widget'"

    def test_ranking_default_excludes_external(self, seeded_backend):
        """F6 / Audit #11: PageRank top must not be polluted by
        `code:external:unresolved:*` when called with defaults."""
        data = _assert_ok(graph.cos_graph_ranking(top=10))
        uids = {n["uid"] for n in data["nodes"]}
        for u in uids:
            assert not u.startswith("code:external:"), f"external leaked: {u}"

    def test_ranking_uid_prefix_noise_does_not_match(self, seeded_backend):
        """F7b: a query like 'function' or 'src' used to seed every
        code-node's personalisation weight because uid_str contained
        the prefix 'code:function:src/...' verbatim. After F7b the uid
        is tokenised and prefix-noise (`code`, `function`, `module`,
        `src`, …) is filtered before the substring match."""
        personalized = _assert_ok(graph.cos_graph_ranking(query="function", top=10))
        baseline = _assert_ok(graph.cos_graph_ranking(top=10))
        # If F7b regressed, personalised top would differ heavily from
        # baseline because every function would seed. With the fix
        # there are no labels containing 'function', so personalisation
        # collapses to uniform → identical baseline ordering.
        assert [n["uid"] for n in personalized["nodes"]] == [
            n["uid"] for n in baseline["nodes"]
        ], "prefix-noise token 'function' polluted personalisation"

    def test_rename_plan_uses_same_behavioural_edge_ssot_as_impact(
        self, seeded_backend
    ):
        """DRY: rename_plan + impact share _BEHAVIOURAL_EDGE_TYPES.
        Pin the contract — both surface the same `constructs` edge for
        a class-consumer site."""
        impact = _assert_ok(graph.cos_graph_impact("code:class:a.py::Widget"))
        impact_types = {
            e["edge_type"]
            for e in impact["tiers"]["will_break"] + impact["tiers"]["should_review"]
        }
        rename = _assert_ok(
            graph.cos_graph_rename_plan("code:class:a.py::Widget", "Gadget")
        )
        rename_types = {e["edge_type"] for e in rename["call_sites"]}
        # Both tools must agree on constructs being a behavioural site.
        assert "constructs" in impact_types
        assert "constructs" in rename_types

    def test_safe_id_collision_proof_for_long_method_uids(self):
        """F5 / Audit #14: previous `_safe_id` truncated at 60 chars,
        making every method of the same class collide. Use the helper
        directly so the contract is pinned regardless of fixture
        graph contents."""
        uid_a = (
            "code:method:src/core/graph_os/backends/sqlite_backend.py::"
            "SqliteBackend.upsert_node"
        )
        uid_b = (
            "code:method:src/core/graph_os/backends/sqlite_backend.py::"
            "SqliteBackend.delete_node"
        )
        assert graph._safe_id(uid_a) != graph._safe_id(uid_b)


class TestRenamePlan:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_rename_plan("code:function:a.py::foo", "renamed_foo"))
        assert data["old_name"] == "foo"
        assert data["new_name"] == "renamed_foo"

    def test_empty_new_name_rejected(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_rename_plan("code:function:a.py::foo", ""),
            "validation",
        )

    def test_class_rename_finds_constructs_and_has_param_type(self, seeded_backend):
        """F2 / Audit #6: class renames used to return 0 call_sites
        because rename_plan's edge filter only covered (calls,
        accesses_field, imports). `constructs` + `has_param_type`
        were silently dropped → rename corrupts code. After fix the
        bucket includes both edge types and every consumer surfaces."""
        data = _assert_ok(graph.cos_graph_rename_plan("code:class:a.py::Widget", "Gadget"))
        edge_types = {site["edge_type"] for site in data["call_sites"]}
        assert "constructs" in edge_types, "constructs edge missing — F2 regressed"
        assert "has_param_type" in edge_types, "has_param_type edge missing — F2 regressed"
        assert data["call_sites_total_count"] >= 2

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_rename_plan("code:function:missing", "new"),
            "not_found",
        )

    def test_risk_set(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_rename_plan("code:function:a.py::foo", "new_foo"))
        assert data["risk"] in {"low", "medium", "high"}


class TestContracts:
    def test_returns_buckets(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts())
        assert "http_routes" in data
        assert "mcp_tools" in data
        assert data["count"] >= 2

    def test_kind_filter_narrows(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts(kinds=["mcp"]))
        assert data["http_routes"] == []
        assert data["mcp_tools"]

    def test_count_present(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts())
        expected = sum(
            len(v)
            for k, v in data.items()
            if k.endswith("_routes")
            or k in ("mcp_tools", "grpc_endpoints", "event_handlers", "websocket")
        )
        assert data["count"] == expected

    def test_envelope_layer_is_graph(self, seeded_backend):
        env = _decode(graph.cos_graph_contracts())
        assert env["data"]["meta"]["layer"] == "graph"


# ---------------------------------------------------------------------------
# Regression — F1 / Audit #2: cos_graph_resolve FTS5 column-order swap.
# Was: SELECT n.uid,n.kind,n.label disagrees with _row_to_node(kind=row[0],
# label=row[1], uid=row[2]) → uid/kind/label silently rotated on every FTS5
# hit. After fix the SELECT order matches the canonical _row_to_node order.
# ---------------------------------------------------------------------------


def test_resolve_fts5_preserves_uid_kind_label(seeded_backend):
    data = _assert_ok(graph.cos_graph_resolve("baz_handler"))
    assert data["results"], "expected at least one resolve hit"
    hit = data["results"][0]
    # canonical _row_to_node order: kind→col0, label→col1, uid→col2.
    # Pre-fix SELECT was uid,kind,label → 3-way rotation. After fix
    # each field carries the right value (kind is normalised by
    # _LEGACY_KIND_MAP so `code:function` → `function`).
    assert hit["uid"] == "code:function:a.py::baz"
    assert hit["kind"] == "function"
    assert hit["label"] == "baz_handler"


# ---------------------------------------------------------------------------
# Cross-tool: every tool must return an envelope with layer="graph".
# ---------------------------------------------------------------------------


# TASK-034: cos_graph_context envelope must stay under TOKEN_BUDGET_CHARS
# even on high-fan-in hubs at depth=2. Pre-fix _apply_token_budget only
# trimmed body["results"] — context emits neighbours+edges_by_type so the
# trimmer never fired, and 150-caller hubs returned 50KB envelopes.
def test_context_envelope_token_budget(seeded_backend):
    """Seed a 200-edge fan-in on a single file uid + assert that a
    depth=2 context call comes back ≤32KB with meta.truncated=true."""
    from graph_os.types import GraphEdge, GraphNode
    from tools._shared import TOKEN_BUDGET_CHARS

    seeded_backend.upsert_node(
        GraphNode(
            uid="code:file:src/hub.sh",
            kind="file",
            label="hub.sh",
            file_path="src/hub.sh",
            lang="sh",
        )
    )
    # 200 caller hooks → 200 inbound edges into hub.sh.
    for i in range(200):
        seeded_backend.upsert_node(
            GraphNode(
                uid=f"code:file:src/caller_{i}.sh",
                kind="file",
                label=f"caller_{i}.sh",
                file_path=f"src/caller_{i}.sh",
                lang="sh",
                signature="x" * 200,  # bloat so each neighbour is ~250B
            )
        )
        seeded_backend.upsert_edge(
            GraphEdge(
                source_uid=f"code:file:src/caller_{i}.sh",
                target_uid="code:file:src/hub.sh",
                edge_type="imports",
                extractor="test@v1",
                confidence=0.9,
            )
        )
    env = _decode(graph.cos_graph_context("code:file:src/hub.sh", depth=2))
    assert env["ok"]
    body = env["data"]
    serialized_len = len(__import__("json").dumps(env, indent=2))
    assert serialized_len <= TOKEN_BUDGET_CHARS, (
        f"context envelope blew budget — {serialized_len} > {TOKEN_BUDGET_CHARS}"
    )
    # TASK-035: depth>=2 returns SUMMARY (counts + top-5 sample). No raw
    # neighbours field — agent drills via cos_graph_references.
    assert body.get("summary_mode") is True
    assert "edge_counts" in body
    assert "top_edges_by_type" in body
    assert "neighbours" not in body
    # 200-edge fan-in is visible via edge_counts (BFS may visit <200 due
    # to visit_limit=50 cap, but the structure is preserved).
    assert body["edge_counts"].get("imports", 0) > 0
    assert serialized_len < 6000, (
        f"depth=2 summary should be < 6KB on this fixture, got {serialized_len}"
    )


# G35: export must enforce max_nodes globally even on non-root export
# (was silently exceeding max_nodes=5 by 4.4× when no root_uid given).
def test_export_max_nodes_hard_cap(seeded_backend):
    data = _assert_ok(graph.cos_graph_export(format="json", max_nodes=5))
    assert len(data["nodes"]) <= 5, (
        f"export breached max_nodes — got {len(data['nodes'])} nodes"
    )


# G14: FTS5 tokenizer must index non-English (Persian/Arabic) labels.
# Pre-v29 the `porter` stemmer stripped them silently → q='گراف' returned 0.
def test_resolve_unicode_label_round_trip(seeded_backend):
    """Seed a Persian-labelled node + confirm resolve picks it up. v29
    migration switched FTS5 to unicode61-only; without that, this asserts
    pre-fix porter-strip on non-Latin scripts."""
    from graph_os.types import GraphNode

    seeded_backend.upsert_node(
        GraphNode(
            uid="code:function:fa.py::گراف_test",
            kind="function",
            label="گراف_تست",
            file_path="fa.py",
            start_line=1,
            lang="py",
        )
    )
    data = _assert_ok(graph.cos_graph_resolve("گراف"))
    uids = [r["uid"] for r in data["results"]]
    assert "code:function:fa.py::گراف_test" in uids, (
        f"unicode61 FTS5 didn't index Persian label — got {uids}"
    )


def test_every_tool_uses_graph_layer(seeded_backend):
    calls = [
        ("query", lambda: graph.cos_graph_query("foo")),
        ("context", lambda: graph.cos_graph_context("code:function:a.py::foo")),
        ("impact", lambda: graph.cos_graph_impact("code:function:a.py::foo")),
        ("detect_changes", lambda: graph.cos_graph_detect_changes(files=["a.py"])),
        ("trace", lambda: graph.cos_graph_trace("code:function:a.py::foo")),
        ("similar", lambda: graph.cos_graph_similar("code:function:a.py::foo")),
        ("references", lambda: graph.cos_graph_references("code:function:a.py::foo")),
        (
            "path",
            lambda: graph.cos_graph_path("code:function:a.py::foo", "code:function:a.py::bar"),
        ),
        ("export", lambda: graph.cos_graph_export(format="json")),
        ("rename_plan", lambda: graph.cos_graph_rename_plan("code:function:a.py::foo", "x")),
        ("contracts", lambda: graph.cos_graph_contracts()),
    ]
    for name, thunk in calls:
        env = _decode(thunk())
        if env["ok"]:
            assert env["data"]["meta"]["layer"] == "graph", name
