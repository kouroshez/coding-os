"""Tests for cos_graph_export smart-blend modes (TASK-141).

Coverage matrix:
  - auto mode blends semantic (60%) + contains (40%) and never returns
    100% contains for non-trivial graphs
  - containment mode is contains-only
  - dependencies mode never includes contains edges
  - processes mode returns synthetic community nodes + member_of edges
  - exclude_kinds default drops doc:frontmatter_key / doc:heading
  - exclude_kinds="" disables filtering
  - explicit exclude_kinds overrides the default set
  - validation: bogus mode rejected with envelope category=validation
  - root_uid path is unchanged (legacy BFS behaviour preserved)
"""

from __future__ import annotations

import json

import pytest

from graph_os.tools import (
    _graph_doctor,
    graph as graph_tools,
)
from graph_os.types import GraphEdge, GraphNode

# ---------------------------------------------------------------------------
# Stub backend (compat with the StubBackend in test_communities.py)
# ---------------------------------------------------------------------------


class _StubBackend:
    backend_id = "stub-export"

    def __init__(self, nodes, edges):
        self._nodes = {n.uid: n for n in nodes}
        self._edges = list(edges)

    def get_node(self, uid):
        return self._nodes.get(uid)

    def sample_nodes(self, *, kind, limit):
        if kind is None:
            return list(self._nodes.values())[:limit]
        return [n for n in self._nodes.values() if n.kind == kind][:limit]

    def list_edges(
        self,
        *,
        source_uid=None,
        target_uid=None,
        edge_types=None,
        confidence_min=0.0,
        limit=100,
    ):
        out = []
        kinds = set(edge_types) if edge_types else None
        for e in self._edges:
            if source_uid is not None and e.source_uid != source_uid:
                continue
            if target_uid is not None and e.target_uid != target_uid:
                continue
            if kinds is not None and e.edge_type not in kinds:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def count_edges(self, edge_type=None):
        if edge_type is None:
            return len(self._edges)
        return sum(1 for e in self._edges if e.edge_type == edge_type)

    def edges_among(
        self, uids, *, edge_types=None, exclude_edge_types=("contains",), limit=100_000
    ):
        members = set(uids)
        wanted = set(edge_types) if edge_types else None
        out = []
        for e in self._edges:
            if e.source_uid not in members or e.target_uid not in members:
                continue
            if e.edge_type in set(exclude_edge_types or ()):
                continue
            if wanted is not None and e.edge_type not in wanted:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out


def _node(uid, kind="code:function", label=None, file_path="src/foo.py"):
    return GraphNode(
        uid=uid,
        kind=kind,
        label=label or uid.split("::")[-1],
        file_path=file_path,
        start_line=1,
        metadata={},
    )


def _edge(src, tgt, etype="calls"):
    return GraphEdge(
        source_uid=src,
        target_uid=tgt,
        edge_type=etype,
        confidence=1.0 if etype == "contains" else 0.8,
        extractor="test@v1",
    )


def _parse(value):
    """`_ok`/`_fail` return a JSON-encoded string envelope."""
    return json.loads(value) if isinstance(value, str) else value


@pytest.fixture
def mixed_backend():
    """Mix of contains + semantic edges + frontmatter noise."""
    nodes = [
        _node("code:file:a.py", kind="code:file"),
        _node("code:module:a", kind="code:module"),
        _node("code:function:a.py::login", label="login"),
        _node("code:function:a.py::verify", label="verify"),
        _node("code:function:a.py::issue_jwt", label="issue_jwt"),
        # Noise nodes that should be filtered by default.
        _node(
            "doc:frontmatter:foo.md::layer",
            kind="doc:frontmatter_key",
            label="layer=engineering",
        ),
        _node(
            "doc:heading:foo.md#intro",
            kind="doc:heading",
            label="Intro",
        ),
    ]
    edges = [
        # Contains spine (high-confidence wins SQL ordering).
        _edge("code:file:a.py", "code:module:a", "contains"),
        _edge("code:module:a", "code:function:a.py::login", "contains"),
        _edge("code:module:a", "code:function:a.py::verify", "contains"),
        _edge("code:module:a", "code:function:a.py::issue_jwt", "contains"),
        _edge(
            "code:module:a",
            "doc:frontmatter:foo.md::layer",
            "contains",
        ),
        _edge(
            "code:module:a",
            "doc:heading:foo.md#intro",
            "contains",
        ),
        # Semantic edges that the legacy export missed.
        _edge(
            "code:function:a.py::login",
            "code:function:a.py::verify",
            "calls",
        ),
        _edge(
            "code:function:a.py::login",
            "code:function:a.py::issue_jwt",
            "calls",
        ),
        _edge(
            "code:function:a.py::verify",
            "code:function:a.py::issue_jwt",
            "calls",
        ),
    ]
    be = _StubBackend(nodes, edges)
    return be


@pytest.fixture(autouse=True)
def _bind_backend(mixed_backend, monkeypatch):
    """Pin the singleton so every cos_graph_export call hits the stub."""
    monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", mixed_backend)
    monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: mixed_backend)
    yield


# ---------------------------------------------------------------------------
# Mode validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unknown_mode_rejected(self):
        res = _parse(graph_tools.cos_graph_export(mode="garbage"))
        assert res["ok"] is False
        assert res["error"]["category"] == "validation"

    def test_unknown_format_rejected(self):
        res = _parse(graph_tools.cos_graph_export(format="rdf"))
        assert res["ok"] is False
        assert res["error"]["category"] == "validation"


# ---------------------------------------------------------------------------
# Mode: auto (export regression guard)
# ---------------------------------------------------------------------------


class TestAutoMode:
    def test_blend_includes_semantic_edges(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=20))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        # Must include both kinds — the bug was 100% contains.
        assert "calls" in edge_types
        assert "contains" in edge_types

    def test_default_mode_is_auto(self):
        # No explicit mode → auto behaviour.
        res = _parse(graph_tools.cos_graph_export(max_nodes=20))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "calls" in edge_types

    def test_noise_filtered_by_default(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=50))
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "doc:frontmatter_key" not in kinds
        assert "doc:heading" not in kinds


# ---------------------------------------------------------------------------
# Mode: containment
# ---------------------------------------------------------------------------


class TestContainmentMode:
    def test_only_contains_edges(self):
        res = _parse(graph_tools.cos_graph_export(mode="containment", max_nodes=50))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert edge_types <= {"contains"}


# ---------------------------------------------------------------------------
# Mode: dependencies
# ---------------------------------------------------------------------------


class TestDependenciesMode:
    def test_no_contains_edges(self):
        res = _parse(graph_tools.cos_graph_export(mode="dependencies", max_nodes=50))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "contains" not in edge_types
        assert "calls" in edge_types


# ---------------------------------------------------------------------------
# Mode: processes
# ---------------------------------------------------------------------------


class TestProcessesMode:
    def test_synthetic_community_nodes(self, monkeypatch):
        # Force a stub Louvain detector that produces one community.
        from graph_os import communities as comm_mod
        from graph_os.communities import Community

        synthetic = Community(
            community_id="community:abc",
            name="login-flow",
            summary="login → verify → issue_jwt",
            priority=0.5,
            member_count=3,
            members=tuple(
                {
                    "uid": uid,
                    "label": uid.split("::")[-1],
                    "kind": "code:function",
                    "step_index": idx,
                    "file_path": "src/foo.py",
                    "start_line": 1,
                }
                for idx, uid in enumerate(
                    [
                        "code:function:a.py::login",
                        "code:function:a.py::verify",
                        "code:function:a.py::issue_jwt",
                    ]
                )
            ),
        )
        monkeypatch.setattr(
            comm_mod,
            "compute_communities",
            lambda be, **kwargs: ([synthetic], {}),
        )

        res = _parse(graph_tools.cos_graph_export(mode="processes", max_nodes=20))
        assert res["ok"] is True
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "community" in kinds
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "member_of_community" in edge_types

    @staticmethod
    def _community(idx: int, size: int):
        from graph_os.communities import Community

        members = tuple(
            {
                "uid": f"code:function:c{idx}.py::fn{j}",
                "label": f"fn{idx}_{j}",
                "kind": "code:function",
                "step_index": j,
                "file_path": f"src/c{idx}.py",
                "start_line": 1,
            }
            for j in range(size)
        )
        return Community(
            community_id=f"community:c{idx}",
            name=f"flow-{idx}",
            summary=f"fn{idx}_0 → fn{idx}_1",
            priority=float(size),
            member_count=size,
            members=members,
        )

    def _bind_communities(self, monkeypatch, communities):
        # The export resolves member uids via be.get_node; register them
        # on the bound stub so the member rows hydrate.
        from graph_os import communities as comm_mod

        be = graph_tools._backend()
        for c in communities:
            for m in c.members:
                be._nodes[m["uid"]] = _node(m["uid"], label=m["label"])
        monkeypatch.setattr(
            comm_mod,
            "compute_communities",
            lambda b, **kwargs: (list(communities), {}),
        )

    def test_at_least_six_community_nodes_surface(self, monkeypatch):
        # TASK-407 / guards the TASK-406 regression: 8 communities where
        # the first holds 400 members. At a 500-node budget the old greedy
        # pass surfaced only ~2 headers; the fair reservation must surface
        # every header.
        communities = [self._community(0, 400)] + [self._community(i, 5) for i in range(1, 8)]
        self._bind_communities(monkeypatch, communities)
        res = _parse(graph_tools.cos_graph_export(mode="processes", max_nodes=500))
        assert res["ok"] is True
        community_nodes = [n for n in res["data"]["nodes"] if n["kind"] == "community"]
        assert len(community_nodes) >= 6

    def test_budget_reserved_across_communities(self, monkeypatch):
        # The 400-member community must not consume the whole budget — its
        # member count in the export is capped at the fair per-community
        # share so every community above min_size appears as its header.
        communities = [self._community(0, 400)] + [self._community(i, 5) for i in range(1, 8)]
        self._bind_communities(monkeypatch, communities)
        res = _parse(graph_tools.cos_graph_export(mode="processes", max_nodes=500))
        nodes = res["data"]["nodes"]
        # Every community above min_size surfaces at least its header node.
        community_ids = {n["uid"] for n in nodes if n["kind"] == "community"}
        assert {f"community:c{i}" for i in range(8)} <= community_ids
        # The top community's members are capped — far below its 400 size.
        edges = res["data"]["edges"]
        top_members = {e["source_uid"] for e in edges if e["target_uid"] == "community:c0"}
        member_budget = 500 - len(community_ids)
        fair_share = max(1, member_budget // len(communities))
        assert len(top_members) <= fair_share


# ---------------------------------------------------------------------------
# Noise filter parametrisation
# ---------------------------------------------------------------------------


class TestExcludeKinds:
    def test_empty_list_disables_filter(self):
        # Pass `[]` to keep all kinds — frontmatter / heading visible.
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=50, exclude_kinds=[]))
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "doc:frontmatter_key" in kinds or "doc:heading" in kinds

    def test_custom_exclude_kinds(self):
        res = _parse(
            graph_tools.cos_graph_export(
                mode="containment",
                max_nodes=50,
                exclude_kinds=["code:module"],
            )
        )
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "code:module" not in kinds


# ---------------------------------------------------------------------------
# Root-walk path is unchanged (don't break existing UI)
# ---------------------------------------------------------------------------


class TestRootWalkUnchanged:
    def test_explicit_root_keeps_legacy_bfs(self):
        res = _parse(
            graph_tools.cos_graph_export(
                root_uid="code:function:a.py::login",
                max_nodes=20,
            )
        )
        assert res["ok"] is True
        # Login + neighbours are reachable; noise is still filtered by default.
        node_uids = {n["uid"] for n in res["data"]["nodes"]}
        assert "code:function:a.py::login" in node_uids


# ---------------------------------------------------------------------------
# max_hops parameter — pinned so a future ruff format or refactor can't
# silently revert to the 3-hop cap that hid subfolder contents in the
# Hub Graph tab (user-reported "depth=all doesn't show 100%").
# ---------------------------------------------------------------------------


@pytest.fixture
def chain_backend():
    """6-link contains chain so depth gating is observable."""
    chain = [f"code:module:level_{i}" for i in range(6)]
    nodes = [_node(uid, kind="code:module", label=uid.split(":")[-1]) for uid in chain]
    edges = [_edge(chain[i], chain[i + 1], "contains") for i in range(len(chain) - 1)]
    return _StubBackend(nodes, edges)


class TestRootWalkMaxHops:
    def test_default_caps_at_three_hops(self, chain_backend, monkeypatch):
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", chain_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: chain_backend)
        res = _parse(
            graph_tools.cos_graph_export(
                root_uid="code:module:level_0",
                max_nodes=50,
            )
        )
        uids = {n["uid"] for n in res["data"]["nodes"]}
        # 3-hop walk reaches level_0..level_3 inclusive (root + 3 hops).
        assert "code:module:level_3" in uids
        assert "code:module:level_5" not in uids, (
            "default max_hops should still cap at 3 hops — backward compat"
        )

    def test_explicit_max_hops_extends_walk(self, chain_backend, monkeypatch):
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", chain_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: chain_backend)
        res = _parse(
            graph_tools.cos_graph_export(
                root_uid="code:module:level_0",
                max_nodes=50,
                max_hops=5,
            )
        )
        uids = {n["uid"] for n in res["data"]["nodes"]}
        # 5-hop walk reaches the full chain.
        assert "code:module:level_5" in uids, (
            "max_hops=5 should walk to the end of the chain — bug was a hardcoded 3"
        )

    def test_max_hops_one_is_just_root_and_neighbours(self, chain_backend, monkeypatch):
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", chain_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: chain_backend)
        res = _parse(
            graph_tools.cos_graph_export(
                root_uid="code:module:level_0",
                max_nodes=50,
                max_hops=1,
            )
        )
        uids = {n["uid"] for n in res["data"]["nodes"]}
        assert "code:module:level_1" in uids
        assert "code:module:level_2" not in uids


# ---------------------------------------------------------------------------
# 8-bucket auto-blend coverage — added 2026-05-23 audit. Doc-link and
# decoration buckets were absent from the previous 6-bucket recipe; the
# blend rendered the doc subgraph invisible (1.5K+ links_to edges).
# ---------------------------------------------------------------------------


@pytest.fixture
def doc_link_backend():
    """Backend with mixed contains + calls + doc-link + decoration edges."""
    nodes = [
        _node("code:file:a.py", kind="code:file"),
        _node("code:function:a.py::foo", label="foo"),
        _node("code:function:a.py::bar", label="bar"),
        _node("doc:file:guide.md", kind="doc_file", label="guide.md"),
        _node("doc:file:other.md", kind="doc_file", label="other.md"),
        _node("code:function:a.py::decorated", label="decorated"),
        _node("code:function:a.py::decorator", label="decorator"),
    ]
    edges = [
        # contains spine
        _edge("code:file:a.py", "code:function:a.py::foo", "contains"),
        _edge("code:file:a.py", "code:function:a.py::bar", "contains"),
        # semantic
        _edge("code:function:a.py::foo", "code:function:a.py::bar", "calls"),
        # doc cross-link — previously invisible in auto mode
        _edge("doc:file:guide.md", "doc:file:other.md", "links_to"),
        _edge("doc:file:guide.md", "code:function:a.py::foo", "references_doc"),
        # decoration
        _edge("code:function:a.py::decorated", "code:function:a.py::decorator", "is_decorated_by"),
    ]
    return _StubBackend(nodes, edges)


class TestAutoBlendNewBuckets:
    def test_auto_mode_includes_doc_link_edges(self, doc_link_backend, monkeypatch):
        """Pre-2026-05-23: auto blend had no doc_link bucket so links_to
        edges only landed if they happened to win the per-bucket race
        in another category. Now there's a dedicated bucket."""
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", doc_link_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: doc_link_backend)
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=100))
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "links_to" in edge_types, (
            "auto blend must include links_to edges via the doc_link bucket"
        )

    def test_auto_mode_includes_decoration_edges(self, doc_link_backend, monkeypatch):
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", doc_link_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: doc_link_backend)
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=100))
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "is_decorated_by" in edge_types, (
            "auto blend must include is_decorated_by edges via the decoration bucket"
        )

    def test_dependencies_mode_includes_doc_link(self, doc_link_backend, monkeypatch):
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", doc_link_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: doc_link_backend)
        res = _parse(graph_tools.cos_graph_export(mode="dependencies", max_nodes=100))
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "links_to" in edge_types or "is_decorated_by" in edge_types


# ---------------------------------------------------------------------------
# stale_paths detector (cos_graph_doctor) — added 2026-05-23 audit.
# Previously zero pytest coverage; the detector removed 3,727 ghost
# nodes from the live repo so silent regression would be very bad.
# ---------------------------------------------------------------------------


class TestStalePathsDetector:
    def test_reports_stale_paths_when_files_missing(self, tmp_path, monkeypatch):
        """Build a real SqliteBackend on a temp DB, seed it with file_path
        nodes pointing to /definitely-not-on-disk, then confirm doctor
        surfaces them as stale_paths."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        db_path = tmp_path / "probe.db"
        backend = SqliteBackend(db_path=str(db_path))
        # Seed two nodes — one with a real path, one with a stale one.
        real_file = tmp_path / "exists.py"
        real_file.write_text("# present on disk\n")
        backend.upsert_node(
            GraphNode(
                uid="code:file:exists.py",
                kind="code:file",
                label="exists.py",
                file_path=str(real_file),
                start_line=1,
                metadata={},
            )
        )
        backend.upsert_node(
            GraphNode(
                uid="code:file:stale.py",
                kind="code:file",
                label="stale.py",
                file_path="/definitely-not-on-disk-stale.py",
                start_line=1,
                metadata={},
            )
        )
        # Point doctor's repo-root probe at our tmp_path so the
        # "exists.py" file resolves there.
        monkeypatch.setattr(
            graph_tools,
            "_repo_root_for_paths",
            lambda: tmp_path,
        )
        captured = backend
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", captured)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: captured)

        res = _parse(graph_tools.cos_graph_doctor())
        assert res["ok"] is True
        categories = {issue["category"] for issue in res["data"]["issues"]}
        assert "stale_paths" in categories
        stale = next(i for i in res["data"]["issues"] if i["category"] == "stale_paths")
        # /definitely-not-on-disk-stale.py is absolute, so doctor checks
        # `tmp_path / "/definitely-not-on-disk-stale.py"` which is itself
        # absolute and not-exists; that counts as stale.
        assert stale["count"] >= 1

    def test_no_false_positives_on_clean_graph(self, tmp_path, monkeypatch):
        from graph_os.backends.sqlite_backend import SqliteBackend

        db_path = tmp_path / "probe.db"
        backend = SqliteBackend(db_path=str(db_path))
        real_file = tmp_path / "x.py"
        real_file.write_text("# ok\n")
        backend.upsert_node(
            GraphNode(
                uid="code:file:x.py",
                kind="code:file",
                label="x.py",
                file_path="x.py",  # relative — resolved against repo_root
                start_line=1,
                metadata={},
            )
        )
        monkeypatch.setattr(graph_tools, "_repo_root_for_paths", lambda: tmp_path)
        monkeypatch.setattr(_graph_doctor, "_repo_root_for_paths", lambda: tmp_path)
        monkeypatch.setattr(_graph_doctor, "_backend", lambda backend=None: captured)
        captured = backend
        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", captured)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: captured)

        res = _parse(graph_tools.cos_graph_doctor())
        categories = {issue["category"] for issue in res["data"]["issues"]}
        assert "stale_paths" not in categories


# ---------------------------------------------------------------------------
# Budget provenance + cap honesty (TASK-402)
# ---------------------------------------------------------------------------


class TestBudgetProvenance:
    def test_meta_reports_requested_and_effective(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=20))
        meta = res["data"]["meta"]
        assert meta["max_nodes_requested"] == 20
        assert meta["max_nodes_effective"] == 20
        assert "result_truncated" in meta

    def test_request_above_old_2000_clamp_is_honored(self):
        # The old silent 2000 clamp cut the Hub's 10k/30k requests —
        # depth=max rendered an incomplete graph with no signal.
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=30000))
        meta = res["data"]["meta"]
        assert meta["max_nodes_effective"] == 30000
        assert meta["result_truncated"] is False  # stub graph is tiny

    def test_request_above_ceiling_flags_truncated(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=60000))
        meta = res["data"]["meta"]
        assert meta["max_nodes_effective"] == 50000
        assert meta["result_truncated"] is True

    def test_cap_hit_flags_truncated(self):
        # Budget smaller than the stub graph -> cap hit -> truncated.
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=2))
        meta = res["data"]["meta"]
        assert meta["result_truncated"] is True

    def test_rooted_walk_reports_effective_hops(self):
        res = _parse(
            graph_tools.cos_graph_export(root_uid="code:file:a.py", max_nodes=20, max_hops=12)
        )
        meta = res["data"]["meta"]
        assert meta["max_hops_effective"] == 12

    def test_overview_has_no_hops(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=20))
        assert res["data"]["meta"]["max_hops_effective"] is None


# ---------------------------------------------------------------------------
# scope=subtree — rooted views stay inside the chosen subtree (TASK-406)
# ---------------------------------------------------------------------------


class TestSubtreeScope:
    def test_subtree_walks_contains_down_only(self):
        # Root at the module: members are the module's children, never the
        # parent file (the old neighborhood walk climbed up and flooded).
        res = _parse(
            graph_tools.cos_graph_export(
                root_uid="code:module:a",
                max_nodes=50,
                max_hops=8,
                scope="subtree",
                exclude_kinds=[],
            )
        )
        uids = {n["uid"] for n in res["data"]["nodes"]}
        assert "code:module:a" in uids
        assert "code:function:a.py::login" in uids
        assert "code:file:a.py" not in uids

    def test_subtree_includes_semantic_edges_among_members(self):
        res = _parse(
            graph_tools.cos_graph_export(
                root_uid="code:module:a",
                max_nodes=50,
                max_hops=8,
                scope="subtree",
                exclude_kinds=[],
            )
        )
        types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "contains" in types
        # calls among login/verify/issue_jwt are inside the subtree.
        assert "calls" in types

    def test_unknown_scope_rejected(self):
        res = _parse(graph_tools.cos_graph_export(scope="galaxy"))
        assert res["ok"] is False
        assert res["error"]["category"] == "validation"
