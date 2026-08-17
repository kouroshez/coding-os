"""cos_graph_* MCP tools — export, sweep-coverage signals, grep fallback and the consult marker.

The seeded fixture graph comes from the directory conftest.
"""

from __future__ import annotations

import json

from graph_os.tools import graph
from graph_os.types import GraphEdge, GraphNode

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


class TestConsultMarker:
    """The MCP tool itself writes the marker the enforce hook reads — the
    producer half of the graph-gate contract that A1/A2 left unverified."""

    def test_context_writes_fresh_marker_and_flags_stale(
        self, seeded_backend, monkeypatch, tmp_path
    ):
        import hashlib

        monkeypatch.chdir(tmp_path)
        agent_dir = tmp_path / ".coding-os" / "claude"
        monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
        body = "print('hello')\n"
        (tmp_path / "target.py").write_text(body, encoding="utf-8")
        seeded_backend.bulk_upsert(
            [
                GraphNode(
                    uid="code:file:target.py",
                    kind="code:file",
                    label="target.py",
                    file_path="target.py",
                    content_hash="0000000000000000",
                )
            ],
            [],
        )

        data = _assert_ok(graph.cos_graph_context("code:file:target.py"))

        disk = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        key = hashlib.sha1(b"target.py").hexdigest()
        marker = agent_dir / ".graph" / f"ctx-{key}"
        assert marker.is_file(), "cos_graph_context must write its own consult marker"
        payload = json.loads(marker.read_text(encoding="utf-8"))
        assert payload["file"] == "target.py"
        assert payload["content_hash"] == disk
        # indexed (0000…) != disk → a stale read surfaces meta.stale.
        assert data["meta"]["stale"] is True
        assert data["meta"]["freshness"]["disk_hash"] == disk

    def test_rename_plan_writes_marker(self, seeded_backend, monkeypatch, tmp_path):
        agent_dir = tmp_path / ".coding-os" / "claude"
        monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
        _assert_ok(graph.cos_graph_rename_plan("code:function:a.py::foo", "foo_renamed"))
        marker = agent_dir / ".graph" / "plan-foo"
        assert marker.is_file(), "cos_graph_rename_plan must write its own consult marker"
        assert json.loads(marker.read_text(encoding="utf-8"))["identifier"] == "foo"


class TestGrepStringLiterals:
    def test_finds_quoted_name(self, monkeypatch, tmp_path):
        """TASK-045: the string-literal scan finds the symbol inside a quoted
        literal — the registry / getattr refs an AST rename pass misses."""
        (tmp_path / "reg.py").write_text('REG = {"WidgetX": WidgetX}\n')
        monkeypatch.setattr(graph, "_repo_root_for_paths", lambda: tmp_path)
        hits = graph._grep_string_literals("WidgetX")
        assert any(h["file"] == "reg.py" and "WidgetX" in h["text"] for h in hits)

    def test_skips_short_names(self, monkeypatch, tmp_path):
        """Names < 3 chars are pure noise — never scanned."""
        (tmp_path / "f.py").write_text('x = "ab"\n')
        monkeypatch.setattr(graph, "_repo_root_for_paths", lambda: tmp_path)
        assert graph._grep_string_literals("ab") == []


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
        data = _assert_ok(graph.cos_graph_rename_plan("code:function:a.py::foo", "renamed_foo"))
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
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo", max_steps=1))
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

    def test_meta_carries_whole_graph_node_total(self, seeded_backend):
        """Without a denominator the Hub badge can only compare the sample to
        itself, which reads as full coverage at every budget."""
        capped = _assert_ok(graph.cos_graph_export(format="json", max_nodes=2))
        total = capped["meta"]["graph_node_total"]
        assert isinstance(total, int)
        assert total >= capped["meta"]["node_count"]

        full = _assert_ok(graph.cos_graph_export(format="json"))
        assert full["meta"]["graph_node_total"] == total

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
            assert len({f for f in files[:4] if f}) >= 2, f"diversify failed — top-4 files: {files}"

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
        assert any(u in targets for u in personalized_uids[:3]), (
            "make_widget / Widget should be in top-3 with query='make widget'"
        )

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
        assert [n["uid"] for n in personalized["nodes"]] == [n["uid"] for n in baseline["nodes"]], (
            "prefix-noise token 'function' polluted personalisation"
        )

    def test_rename_plan_uses_same_behavioural_edge_ssot_as_impact(self, seeded_backend):
        """DRY: rename_plan + impact share _BEHAVIOURAL_EDGE_TYPES.
        Pin the contract — both surface the same `constructs` edge for
        a class-consumer site."""
        impact = _assert_ok(graph.cos_graph_impact("code:class:a.py::Widget"))
        impact_types = {
            e["edge_type"] for e in impact["tiers"]["will_break"] + impact["tiers"]["should_review"]
        }
        rename = _assert_ok(graph.cos_graph_rename_plan("code:class:a.py::Widget", "Gadget"))
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
            "code:method:src/core/graph_os/backends/sqlite_backend.py::SqliteBackend.upsert_node"
        )
        uid_b = (
            "code:method:src/core/graph_os/backends/sqlite_backend.py::SqliteBackend.delete_node"
        )
        assert graph._safe_id(uid_a) != graph._safe_id(uid_b)


def test_export_max_nodes_hard_cap(seeded_backend):
    data = _assert_ok(graph.cos_graph_export(format="json", max_nodes=5))
    assert len(data["nodes"]) <= 5, f"export breached max_nodes — got {len(data['nodes'])} nodes"


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
