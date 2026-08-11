"""cos_graph_* MCP tools — impact, references, path, rename and contract surfaces.

The seeded fixture graph comes from the directory conftest.
"""

from __future__ import annotations

import json

from graph_os.tools import graph

# ---------------------------------------------------------------------------
# Fixtures
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
            tight_data = _assert_ok(graph.cos_graph_references("code:function:a.py::foo", limit=1))
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
            graph.cos_graph_path("code:function:a.py::foo", "code:function:a.py::baz")
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
            graph.cos_graph_path("code:function:a.py::foo", "code:function:a.py::baz")
        )
        if data["edges"]:
            for e in data["edges"]:
                assert "traversal_direction" in e
                assert e["traversal_direction"] in {"forward", "reverse"}


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
