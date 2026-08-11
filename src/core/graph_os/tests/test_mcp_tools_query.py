"""cos_graph_* MCP tools — query, context, trace and change detection.

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
        data = _assert_ok(graph.cos_graph_context("code:function:a.py::foo", visit_limit=1))
        assert data["meta"]["walk_truncated"] is True
        assert data["meta"]["visit_limit"] == 1


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


def test_context_envelope_token_budget(seeded_backend):
    """Seed a 200-edge fan-in on a single file uid + assert that a
    depth=2 context call comes back ≤32KB with meta.truncated=true."""
    from tools._shared import TOKEN_BUDGET_CHARS

    from graph_os.types import GraphEdge, GraphNode

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
    # depth>=2 returns SUMMARY (counts + top-5 sample). No raw
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


def test_harakat_query_folds_to_base_form():
    """A harakat-bearing Arabic/Persian query folds to its harakat-free base, so
    both forms produce the identical FTS5 query (cross-form match, TASK-485)."""
    bare = "علم"
    voweled = "عِلْم"  # same word with kasra (U+0650) + sukun (U+0652)
    assert voweled != bare
    assert graph._fold_harakat(voweled) == bare
    # The two forms must yield the same FTS5 MATCH string — this is the
    # query-side half of harakat-insensitive search.
    assert graph._fts5_safe_query(voweled) == graph._fts5_safe_query(bare)
    assert graph._fts5_safe_query(bare)  # non-empty (token survived)


def test_escape_stays_syntax_only_never_html_encodes():
    """_escape() is mermaid/dot syntax-safe and must NOT HTML-encode (TASK-486):
    HTML-context escaping belongs at the render boundary, not here. Locks the
    byte-for-byte CLI/.mmd/.dot contract against a well-meaning XSS 'fix'."""
    payload = "<img src=x onerror=alert(1)>"
    escaped = graph._escape(payload)
    # angle brackets + ampersand survive verbatim — NOT &lt; / &gt; / &amp;
    assert "<img" in escaped and ">" in escaped
    assert "&lt;" not in escaped
    assert "&gt;" not in escaped
    assert "&amp;" not in escaped
    # the mermaid/dot-breaking chars ARE still neutralised
    assert graph._escape('a"b\\c') == "a'b/c"
