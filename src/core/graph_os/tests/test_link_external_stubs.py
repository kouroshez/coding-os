"""link_external_stubs: stub-edge rewriting to real cross-file targets."""

from __future__ import annotations

import sqlite3

from graph_os.backends.sqlite_backend import SqliteBackend
from graph_os.types import GraphEdge, GraphNode


def _migrated_conn() -> sqlite3.Connection:
    import database as thinking_os_db

    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def test_resolves_relative_import_to_real_symbol():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    real = GraphNode(
        uid="code:function:core/graph_os/types.py::normalize_kind",
        kind="code:function",
        label="normalize_kind",
        file_path="core/graph_os/types.py",
    )
    caller_file = GraphNode(
        uid="code:file:core/graph_os/backends/sqlite_backend.py",
        kind="code:file",
        label="sqlite_backend.py",
        file_path="core/graph_os/backends/sqlite_backend.py",
    )
    stub = GraphNode(
        uid="code:external:graph_os.types:normalize_kind",
        kind="code:external",
        label="normalize_kind",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [real, caller_file, stub],
        [
            GraphEdge(
                source_uid=caller_file.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.4,
            )
        ],
    )

    rewrites = backend.link_external_stubs()
    assert rewrites == 1

    edges = list(backend.list_edges(edge_types=("calls",), limit=10))
    assert len(edges) == 1
    assert edges[0].target_uid == real.uid


def test_link_no_abort_on_duplicate_rewrite():
    """TASK-043: a caller reaching the same real symbol via two module
    spellings must NOT abort the whole linker pass with a UNIQUE
    IntegrityError. OR IGNORE skips the duplicate rewrite; the real edge
    from the first spelling survives."""
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:pkg/tools/_shared.py::fail",
        kind="code:function",
        label="fail",
        file_path="pkg/tools/_shared.py",
    )
    caller = GraphNode(
        uid="code:function:pkg/board.py::handler",
        kind="code:function",
        label="handler",
        file_path="pkg/board.py",
    )
    st1 = GraphNode(
        uid="code:external:tools._shared:fail",
        kind="code:external",
        label="fail",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    st2 = GraphNode(
        uid="code:external:pkg.tools._shared:fail",
        kind="code:external",
        label="fail",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [real, caller, st1, st2],
        [
            GraphEdge(
                source_uid=caller.uid,
                target_uid=st1.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.4,
            ),
            GraphEdge(
                source_uid=caller.uid,
                target_uid=st2.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.4,
            ),
        ],
    )
    backend.link_external_stubs()  # must NOT raise IntegrityError
    n = conn.execute("SELECT id FROM graph_nodes WHERE uid=?", (real.uid,)).fetchone()[0]
    ib = conn.execute(
        "SELECT COUNT(*) FROM graph_edges_v12 WHERE target_id=? AND edge_type='calls'",
        (n,),
    ).fetchone()[0]
    assert ib == 1  # caller resolves to real exactly once (deduped, not aborted)


def test_skips_ambiguous_multi_module_match():
    """TASK-043: when a stub's module suffix matches MORE THAN ONE real file
    (same leaf label in two modules), skip rather than guess a false edge."""
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real_a = GraphNode(
        uid="code:function:pkg/a/utils.py::helper",
        kind="code:function",
        label="helper",
        file_path="pkg/a/utils.py",
    )
    real_b = GraphNode(
        uid="code:function:pkg/b/utils.py::helper",
        kind="code:function",
        label="helper",
        file_path="pkg/b/utils.py",
    )
    caller = GraphNode(
        uid="code:file:pkg/c/caller.py",
        kind="code:file",
        label="caller.py",
        file_path="pkg/c/caller.py",
    )
    stub = GraphNode(
        uid="code:external:utils:helper",
        kind="code:external",
        label="helper",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [real_a, real_b, caller, stub],
        [
            GraphEdge(
                source_uid=caller.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.4,
            )
        ],
    )
    # Both pkg/a/utils.py and pkg/b/utils.py end with /utils.py → ambiguous.
    assert backend.link_external_stubs() == 0
    edges = list(backend.list_edges(edge_types=("calls",), limit=10))
    assert edges[0].target_uid == stub.uid  # left on the stub, no guessed edge


def test_skips_unresolvable_stubs():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    src_file = GraphNode(
        uid="code:file:foo.py",
        kind="code:file",
        label="foo.py",
        file_path="foo.py",
    )
    stub = GraphNode(
        uid="code:external:nonexistent.module:missing_fn",
        kind="code:external",
        label="missing_fn",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [src_file, stub],
        [
            GraphEdge(
                source_uid=src_file.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.3,
            )
        ],
    )

    rewrites = backend.link_external_stubs()
    assert rewrites == 0


def test_calls_to_class_promoted_to_constructs_on_rewrite():
    """W6.1 (N2): when a stub `code:external:<mod>:<Class>` resolves to a
    real `code:class:*` node and the inbound edge_type is `calls` (i.e. a
    constructor invocation that the extractor couldn't classify at emit
    time because the target was still an external stub), the rewrite
    must promote the edge_type from `calls` to `constructs`.
    """
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    real_class = GraphNode(
        uid="code:class:core/foo.py::Foo",
        kind="class",
        label="Foo",
        file_path="core/foo.py",
    )
    caller_file = GraphNode(
        uid="code:file:core/bar.py",
        kind="code:file",
        label="bar.py",
        file_path="core/bar.py",
    )
    stub = GraphNode(
        uid="code:external:core.foo:Foo",
        kind="code:external",
        label="Foo",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [real_class, caller_file, stub],
        [
            GraphEdge(
                source_uid=caller_file.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.9,
            )
        ],
    )

    rewrites = backend.link_external_stubs()
    assert rewrites == 1

    edges_calls = list(backend.list_edges(edge_types=("calls",), limit=10))
    edges_ctor = list(backend.list_edges(edge_types=("constructs",), limit=10))
    # Edge was promoted: no longer `calls`, surfaces as `constructs`.
    assert edges_calls == []
    assert len(edges_ctor) == 1
    assert edges_ctor[0].target_uid == real_class.uid


def test_calls_to_function_preserved_on_rewrite():
    """W6.1 (N2 invariant): non-class targets must NOT be promoted to
    `constructs` — only class-resolved stubs flip. A function rewrite
    keeps `edge_type='calls'`.
    """
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    real_fn = GraphNode(
        uid="code:function:core/foo.py::helper",
        kind="function",
        label="helper",
        file_path="core/foo.py",
    )
    caller_file = GraphNode(
        uid="code:file:core/bar.py",
        kind="code:file",
        label="bar.py",
        file_path="core/bar.py",
    )
    stub = GraphNode(
        uid="code:external:core.foo:helper",
        kind="code:external",
        label="helper",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [real_fn, caller_file, stub],
        [
            GraphEdge(
                source_uid=caller_file.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.9,
            )
        ],
    )

    rewrites = backend.link_external_stubs()
    assert rewrites == 1

    edges_calls = list(backend.list_edges(edge_types=("calls",), limit=10))
    edges_ctor = list(backend.list_edges(edge_types=("constructs",), limit=10))
    assert len(edges_calls) == 1
    assert edges_calls[0].target_uid == real_fn.uid
    assert edges_ctor == []


def test_label_with_special_chars_does_not_match_unrelated():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    other = GraphNode(
        uid="code:function:src/other.py::foo",
        kind="code:function",
        label="foo",
        file_path="src/other.py",
    )
    src_file = GraphNode(
        uid="code:file:src/caller.py",
        kind="code:file",
        label="caller.py",
        file_path="src/caller.py",
    )
    stub = GraphNode(
        uid="code:external:totally.unrelated:foo",
        kind="code:external",
        label="foo",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert(
        [other, src_file, stub],
        [
            GraphEdge(
                source_uid=src_file.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
                confidence=0.4,
            )
        ],
    )

    rewrites = backend.link_external_stubs()
    assert rewrites == 0


# ---------------------------------------------------------------------------
# link_import_bindings — import_ node → real symbol (TASK-402)
# ---------------------------------------------------------------------------


def _import_node(file_path: str, name: str, module: str) -> GraphNode:
    return GraphNode(
        uid=f"code:import:{file_path}::{name}",
        kind="code:import",
        label=f"import {name}",
        file_path=file_path,
        metadata={
            "extractor": "code_python@v1",
            "imported": name,
            "source_module": module,
            "wildcard": False,
        },
    )


def test_import_binding_links_to_unique_symbol():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:src/core/thinking_os/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="src/core/thinking_os/database.py",
    )
    importer = _import_node("src/cli/graph_commands.py", "init_db", "thinking_os.database")
    backend.bulk_upsert([real, importer], [])

    linked = backend.link_import_bindings()
    assert linked == 1
    row = conn.execute(
        "SELECT e.edge_type, e.extractor FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id=e.source_id AND s.uid=? "
        "JOIN graph_nodes t ON t.id=e.target_id AND t.uid=?",
        (importer.uid, real.uid),
    ).fetchone()
    assert row is not None
    assert row[0] == "imports"
    assert row[1] == "import_linker@v1"


def test_import_binding_resolves_path_hacked_alias():
    # `from database import init_db` (sys.path hack) — module suffix match.
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:src/core/thinking_os/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="src/core/thinking_os/database.py",
    )
    importer = _import_node("tests/test_cli.py", "init_db", "database")
    backend.bulk_upsert([real, importer], [])
    assert backend.link_import_bindings() == 1


def test_import_binding_skips_ambiguous_target():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real_a = GraphNode(
        uid="code:function:a/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="a/database.py",
    )
    real_b = GraphNode(
        uid="code:function:b/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="b/database.py",
    )
    importer = _import_node("x.py", "init_db", "database")
    backend.bulk_upsert([real_a, real_b, importer], [])
    assert backend.link_import_bindings() == 0


def test_import_binding_idempotent():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:pkg/mod.py::helper",
        kind="code:function",
        label="helper",
        file_path="pkg/mod.py",
    )
    importer = _import_node("app.py", "helper", "pkg.mod")
    backend.bulk_upsert([real, importer], [])
    assert backend.link_import_bindings() == 1
    assert backend.link_import_bindings() == 0


def test_import_binding_file_scoped():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:pkg/mod.py::helper",
        kind="code:function",
        label="helper",
        file_path="pkg/mod.py",
    )
    in_scope = _import_node("app.py", "helper", "pkg.mod")
    out_of_scope = _import_node("other.py", "helper", "pkg.mod")
    backend.bulk_upsert([real, in_scope, out_of_scope], [])
    assert backend.link_import_bindings(file_path="app.py") == 1


# ---------------------------------------------------------------------------
# contains_ancestors_bulk — set-wise spine closure (TASK-403)
# ---------------------------------------------------------------------------


def _spine_fixture(backend: SqliteBackend) -> None:
    nodes = [
        GraphNode(uid="folder:src", kind="folder", label="src", file_path="src"),
        GraphNode(uid="folder:src/core", kind="folder", label="core", file_path="src/core"),
        GraphNode(
            uid="code:file:src/core/a.py", kind="code:file", label="a.py",
            file_path="src/core/a.py",
        ),
        GraphNode(
            uid="code:function:src/core/a.py::f", kind="code:function", label="f",
            file_path="src/core/a.py",
        ),
        GraphNode(
            uid="doc:file:docs/x.md", kind="doc:file", label="x.md", file_path="docs/x.md",
        ),
        GraphNode(uid="folder:docs", kind="folder", label="docs", file_path="docs"),
    ]
    edges = [
        GraphEdge(source_uid="folder:src", target_uid="folder:src/core",
                  edge_type="contains", extractor="t", confidence=1.0),
        GraphEdge(source_uid="folder:src/core", target_uid="code:file:src/core/a.py",
                  edge_type="contains", extractor="t", confidence=1.0),
        GraphEdge(source_uid="code:file:src/core/a.py",
                  target_uid="code:function:src/core/a.py::f",
                  edge_type="contains", extractor="t", confidence=1.0),
        GraphEdge(source_uid="folder:docs", target_uid="doc:file:docs/x.md",
                  edge_type="contains", extractor="t", confidence=1.0),
    ]
    backend.bulk_upsert(nodes, edges)


def test_bulk_closure_returns_full_ancestor_chain():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    _spine_fixture(backend)
    ancestors, spine_edges = backend.contains_ancestors_bulk(
        ["code:function:src/core/a.py::f"]
    )
    ancestor_uids = {n.uid for n in ancestors}
    assert ancestor_uids == {"folder:src", "folder:src/core", "code:file:src/core/a.py"}
    pairs = {(e.source_uid, e.target_uid) for e in spine_edges}
    assert ("folder:src", "folder:src/core") in pairs
    assert ("code:file:src/core/a.py", "code:function:src/core/a.py::f") in pairs


def test_bulk_closure_multi_leaf_no_duplicates():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    _spine_fixture(backend)
    ancestors, _ = backend.contains_ancestors_bulk(
        ["code:function:src/core/a.py::f", "code:file:src/core/a.py", "doc:file:docs/x.md"]
    )
    ancestor_uids = [n.uid for n in ancestors]
    assert len(ancestor_uids) == len(set(ancestor_uids))
    assert "folder:docs" in ancestor_uids
    # inputs are never echoed back as ancestors
    assert "doc:file:docs/x.md" not in ancestor_uids


def test_bulk_closure_empty_input():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    assert backend.contains_ancestors_bulk([]) == ([], [])


# ---------------------------------------------------------------------------
# edges_among — semantic overlay for subtree exports (TASK-406)
# ---------------------------------------------------------------------------


def test_edges_among_returns_only_in_set_semantic_edges():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    inside_a = GraphNode(uid="code:function:m.py::a", kind="code:function", label="a", file_path="m.py")
    inside_b = GraphNode(uid="code:function:m.py::b", kind="code:function", label="b", file_path="m.py")
    outside = GraphNode(uid="code:function:x.py::c", kind="code:function", label="c", file_path="x.py")
    holder = GraphNode(uid="code:file:m.py", kind="code:file", label="m.py", file_path="m.py")
    backend.bulk_upsert(
        [inside_a, inside_b, outside, holder],
        [
            GraphEdge(source_uid=inside_a.uid, target_uid=inside_b.uid, edge_type="calls",
                      extractor="t", confidence=0.9),
            GraphEdge(source_uid=inside_a.uid, target_uid=outside.uid, edge_type="calls",
                      extractor="t", confidence=0.9),
            GraphEdge(source_uid=holder.uid, target_uid=inside_a.uid, edge_type="contains",
                      extractor="t", confidence=1.0),
        ],
    )
    edges = backend.edges_among([inside_a.uid, inside_b.uid, holder.uid])
    pairs = {(e.source_uid, e.target_uid, e.edge_type) for e in edges}
    assert (inside_a.uid, inside_b.uid, "calls") in pairs
    assert all(e.target_uid != outside.uid for e in edges)
    assert all(e.edge_type != "contains" for e in edges)
