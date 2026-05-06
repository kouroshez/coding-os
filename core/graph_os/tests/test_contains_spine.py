"""graph_os — S3 CONTAINS spine + NodeKind enum regression suite.

DEPENDS:  graph_os.types, graph_os.extractors.*.
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import (
    code_python,
    code_shell,
    code_ts,
    code_yaml,
    contracts,
    md_links,
    task_deps,
)
from graph_os.types import NodeKind, normalize_kind


# ---------------------------------------------------------------------------
# NodeKind / normalize_kind
# ---------------------------------------------------------------------------


class TestNodeKindEnum:
    def test_core_members_present(self):
        # Task scope lists these as the minimum required vocabulary.
        required = {
            "folder", "file", "class", "method", "function",
            "variable", "import_", "route", "tool", "event", "task",
            "doc_file", "doc_heading", "rule", "skill", "contract",
            "community",
        }
        values = {k.value for k in NodeKind}
        missing = required - values
        assert not missing, f"NodeKind missing required members: {missing}"

    def test_from_any_legacy_code_prefixes(self):
        assert NodeKind.from_any("code:file") is NodeKind.FILE
        assert NodeKind.from_any("code:function") is NodeKind.FUNCTION
        assert NodeKind.from_any("code:method") is NodeKind.METHOD
        assert NodeKind.from_any("code:class") is NodeKind.CLASS
        assert NodeKind.from_any("code:import") is NodeKind.IMPORT_
        assert NodeKind.from_any("code:interface") is NodeKind.INTERFACE

    def test_from_any_legacy_doc_prefixes(self):
        assert NodeKind.from_any("doc:file") is NodeKind.DOC_FILE
        assert NodeKind.from_any("doc:heading") is NodeKind.DOC_HEADING

    def test_from_any_legacy_cos_prefixes(self):
        assert NodeKind.from_any("cos:route") is NodeKind.ROUTE
        assert NodeKind.from_any("cos:mcp_tool") is NodeKind.MCP_TOOL
        assert NodeKind.from_any("cos:hook") is NodeKind.HOOK

    def test_from_any_canonical_shortform(self):
        assert NodeKind.from_any("folder") is NodeKind.FOLDER
        assert NodeKind.from_any("file") is NodeKind.FILE
        assert NodeKind.from_any("method") is NodeKind.METHOD

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError):
            NodeKind.from_any("")
        with pytest.raises(ValueError):
            NodeKind.from_any("bogus:kind:unknown")

    def test_normalize_kind_is_idempotent(self):
        for raw in ("code:file", "file", "doc:heading", "doc_heading"):
            first = normalize_kind(raw)
            second = normalize_kind(first.value)
            assert first is second


# ---------------------------------------------------------------------------
# Folder-spine emission per extractor
# ---------------------------------------------------------------------------


def _contains_edges(result) -> list[tuple[str, str]]:
    return [
        (e.source_uid, e.target_uid)
        for e in result.edges
        if e.edge_type == "contains"
    ]


def _folder_nodes(result) -> list:
    return [n for n in result.nodes if n.kind == "folder"]


class TestFolderSpine:
    def test_python_emits_folder_chain(self):
        src = textwrap.dedent(
            """
            class Foo:
                def bar(self):
                    return 1
            """
        )
        r = code_python.extract("core/graph_os/extractors/sample.py", src)
        # Folder chain: folder:. → folder:core → folder:core/graph_os → ...
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:." in folder_uids
        assert "folder:core" in folder_uids
        assert "folder:core/graph_os" in folder_uids
        assert "folder:core/graph_os/extractors" in folder_uids
        # Contains edge from deepest folder → file.
        edges = set(_contains_edges(r))
        assert (
            "folder:core/graph_os/extractors",
            "code:file:core/graph_os/extractors/sample.py",
        ) in edges

    def test_md_emits_folder_chain(self):
        r = md_links.extract("docs/sample.md", "# Title\n\n[x](y.md)\n")
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:." in folder_uids
        assert "folder:docs" in folder_uids

    def test_shell_emits_folder_chain(self):
        r = code_shell.extract("core/hooks/x.sh", "greet(){ echo hi; }\n")
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:core" in folder_uids
        assert "folder:core/hooks" in folder_uids

    def test_yaml_emits_folder_chain(self):
        r = code_yaml.extract("core/hooks/registry.yaml", "hooks: []\n")
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:core/hooks" in folder_uids

    def test_ts_emits_folder_chain(self):
        r = code_ts.extract(
            "core/web/ui/src/App.tsx",
            "export function App(){ return null }\n",
        )
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:core/web/ui/src" in folder_uids

    def test_contracts_emits_folder_chain(self):
        r = contracts.extract(
            "core/api/routes.py",
            '@app.get("/x")\ndef hello(): return 1\n',
        )
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:core/api" in folder_uids

    def test_task_deps_emits_folder_chain(self):
        r = task_deps.extract("docs/tasks/TASK-999-sample.md", "# random\n")
        folder_uids = {n.uid for n in _folder_nodes(r)}
        assert "folder:docs/tasks" in folder_uids

    def test_spine_idempotent_across_extractors(self):
        # Same folder uid must be emitted by different extractors so
        # bulk_upsert de-duplicates. Simple equality check on the uid
        # is enough — backend is idempotent on uid.
        r_py = code_python.extract("core/a.py", "x = 1\n")
        r_md = md_links.extract("core/a.md", "# title\n")
        py_uids = {n.uid for n in _folder_nodes(r_py) if n.uid == "folder:core"}
        md_uids = {n.uid for n in _folder_nodes(r_md) if n.uid == "folder:core"}
        assert py_uids == md_uids == {"folder:core"}


# ---------------------------------------------------------------------------
# Connected spine on the hand-rolled fixture
# ---------------------------------------------------------------------------


_PY_FIXTURE_A = textwrap.dedent(
    """
    class Alpha:
        def a1(self):
            return 1

        def a2(self):
            return 2

    class Beta:
        def b1(self):
            return 3
    """
)

_PY_FIXTURE_B = textwrap.dedent(
    """
    class Gamma:
        def g1(self):
            return 4

        def g2(self):
            return 5
    """
)


class TestConnectedSpineFixture:
    """Fixture: 1 folder (``sample_repo/``) → 2 files → 3 classes → 5 methods."""

    def _collect(self) -> tuple[list, list]:
        nodes: list = []
        edges: list = []
        for path, content in (
            ("sample_repo/module_a.py", _PY_FIXTURE_A),
            ("sample_repo/module_b.py", _PY_FIXTURE_B),
        ):
            r = code_python.extract(path, content)
            nodes.extend(r.nodes)
            edges.extend(r.edges)
        return nodes, edges

    def test_all_expected_kinds_present(self):
        nodes, _ = self._collect()
        kinds = {n.kind for n in nodes}
        # Post-S3 extractors continue emitting legacy colon-prefixed
        # strings; normalize_kind coerces them to canonical forms.
        normalized = {normalize_kind(k) for k in kinds}
        assert NodeKind.FOLDER in normalized
        assert NodeKind.FILE in normalized
        assert NodeKind.CLASS in normalized
        assert NodeKind.METHOD in normalized

    def test_connected_spine_from_root_to_methods(self):
        nodes, edges = self._collect()
        # Build adjacency on contains edges.
        contains_children: dict[str, list[str]] = {}
        for e in edges:
            if e.edge_type == "contains":
                contains_children.setdefault(e.source_uid, []).append(
                    e.target_uid
                )

        # BFS from repo root; every leaf method must be reachable.
        root = "folder:."
        assert root in contains_children or any(
            root == n.uid for n in nodes
        )
        reachable: set[str] = {root}
        frontier = [root]
        while frontier:
            nxt: list[str] = []
            for uid in frontier:
                for child in contains_children.get(uid, []):
                    if child not in reachable:
                        reachable.add(child)
                        nxt.append(child)
            frontier = nxt

        method_uids = [n.uid for n in nodes if n.kind == "code:method"]
        assert len(method_uids) == 5
        missing = [m for m in method_uids if m not in reachable]
        assert not missing, f"methods unreachable from repo root: {missing}"

    def test_no_duplicate_contains_edges_within_one_extract(self):
        """Within a single extract() run, (source, target) for contains
        must not repeat — multi-file runs DO repeat the shared folder
        chain, but the backend's UNIQUE (source, target, edge_type,
        extractor) constraint de-dupes on bulk_upsert. This test checks
        the per-file invariant.
        """
        for path, content in (
            ("sample_repo/module_a.py", _PY_FIXTURE_A),
            ("sample_repo/module_b.py", _PY_FIXTURE_B),
        ):
            r = code_python.extract(path, content)
            pairs: dict[tuple[str, str], int] = {}
            for e in r.edges:
                if e.edge_type != "contains":
                    continue
                key = (e.source_uid, e.target_uid)
                pairs[key] = pairs.get(key, 0) + 1
            dups = {k: v for k, v in pairs.items() if v > 1}
            assert not dups, (
                f"duplicate contains edges in single extract of {path}: {dups}"
            )


# ---------------------------------------------------------------------------
# Migration v16 data migration
# ---------------------------------------------------------------------------


class TestMigrationV16:
    def test_rewrites_legacy_kinds(self, tmp_path):
        """Insert legacy-kind rows into a throwaway DB then apply v16."""
        import sqlite3
        import db  # type: ignore

        db_path = str(tmp_path / "migration-v16.db")
        conn = sqlite3.connect(db_path)
        # Run migrations up through v15 first by calling init_db, which
        # applies all currently-registered MIGRATIONS.
        conn.close()

        # First open via init_db so schema is fully in place (including
        # the v16 migration — we'll pre-seed legacy rows, then re-run).
        conn = db.init_db(db_path)

        # Insert fake legacy rows directly (created_at/updated_at NOT NULL).
        conn.execute("DELETE FROM graph_nodes")
        conn.executemany(
            "INSERT INTO graph_nodes(uid,kind,label,created_at,updated_at) "
            "VALUES (?,?,?,strftime('%s','now'),strftime('%s','now'))",
            [
                ("code:function:foo::bar", "code:function", "bar"),
                ("code:method:foo::Baz.qux", "code:method", "qux"),
                ("doc:file:docs/x.md", "doc:file", "x.md"),
                ("task:file:TASK-001", "task:file", "TASK-001"),
                ("cos:route:GET:/x", "cos:route", "GET /x"),
            ],
        )
        conn.commit()

        # Force re-run of v16: remove v16+ rows from schema_version so
        # run_migrations picks v16 (and any later idempotent migrations)
        # up again. Later migrations (v17 file_index_state) must be
        # idempotent under re-run.
        conn.execute("DELETE FROM schema_version WHERE version >= 16")
        conn.commit()
        db.run_migrations(conn)

        rows = conn.execute(
            "SELECT uid, kind FROM graph_nodes ORDER BY uid"
        ).fetchall()
        kind_by_uid = {r[0]: r[1] for r in rows}

        assert kind_by_uid["code:function:foo::bar"] == "function"
        assert kind_by_uid["code:method:foo::Baz.qux"] == "method"
        assert kind_by_uid["doc:file:docs/x.md"] == "doc_file"
        assert kind_by_uid["task:file:TASK-001"] == "task"
        assert kind_by_uid["cos:route:GET:/x"] == "route"
        conn.close()
