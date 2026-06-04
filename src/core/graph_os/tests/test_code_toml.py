"""Tests for graph_os.extractors.code_toml — pyproject + Cargo dependency extraction.

Pure extractor (``extract(path, content)``). Targets the pyproject /
Cargo emitters, version-spec stripping, workspace members, subtype
dispatch, and the malformed-TOML parse-error path.
"""

from __future__ import annotations

import textwrap

from graph_os.extractors import code_toml


def _extract(src: str, *, path: str):
    return code_toml.extract(path, textwrap.dedent(src).lstrip("\n"))


# ---------------------------------------------------------------------------
# Subtype detection + basics
# ---------------------------------------------------------------------------


class TestSubtypeAndBasics:
    def test_detect_subtype(self):
        assert code_toml._detect_subtype("pyproject.toml") == "pyproject"
        assert code_toml._detect_subtype("Cargo.toml") == "cargo"
        assert code_toml._detect_subtype("ruff.toml") == "generic"

    def test_generic_toml_only_file_node(self):
        r = _extract("[tool.ruff]\nline-length = 100\n", path="ruff.toml")
        assert any(n.kind == "code:file" for n in r.nodes)
        # No dependency / crate nodes for a generic config.
        assert not any(n.kind in ("dependency", "contract") for n in r.nodes)

    def test_malformed_toml_records_parse_error(self):
        r = _extract("[project\nname = broken", path="pyproject.toml")
        assert any(pe.kind == "toml_decode" for pe in r.parse_errors)
        assert any(n.kind == "code:file" for n in r.nodes)


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


class TestPyproject:
    def test_project_name_declares_package(self):
        r = _extract('[project]\nname = "myapp"\n', path="pyproject.toml")
        assert any(n.kind == "dependency" and n.uid == "pypi:package:myapp" for n in r.nodes)
        assert any(
            e.edge_type == "declares" and e.target_uid == "pypi:package:myapp" for e in r.edges
        )

    def test_dependencies_with_version_specs_stripped(self):
        r = _extract(
            """
            [project]
            name = "app"
            dependencies = [
                "click>=8.0",
                "pytest[extra]==7.4",
                "httpx; python_version < '3.11'",
            ]
            """,
            path="pyproject.toml",
        )
        targets = {e.target_uid for e in r.edges if e.edge_type == "imports"}
        assert "pypi:package:click" in targets
        assert "pypi:package:pytest" in targets
        assert "pypi:package:httpx" in targets

    def test_optional_dependencies(self):
        r = _extract(
            """
            [project]
            name = "app"
            [project.optional-dependencies]
            rag = ["sentence-transformers"]
            """,
            path="pyproject.toml",
        )
        assert any(
            e.target_uid == "pypi:package:sentence-transformers" and e.edge_type == "imports"
            for e in r.edges
        )

    def test_pep735_dependency_groups(self):
        r = _extract(
            """
            [project]
            name = "app"
            [dependency-groups]
            dev = ["ruff", "mypy"]
            """,
            path="pyproject.toml",
        )
        targets = {e.target_uid for e in r.edges if e.edge_type == "imports"}
        assert "pypi:package:ruff" in targets and "pypi:package:mypy" in targets

    def test_scripts_emit_tool_nodes(self):
        r = _extract(
            """
            [project]
            name = "app"
            [project.scripts]
            mycli = "app.cli:main"
            """,
            path="pyproject.toml",
        )
        assert any(n.kind == "tool" and n.label == "mycli" for n in r.nodes)


# ---------------------------------------------------------------------------
# Cargo.toml
# ---------------------------------------------------------------------------


class TestCargo:
    def test_package_declares_crate(self):
        r = _extract('[package]\nname = "mycrate"\nversion = "0.1.0"\n', path="Cargo.toml")
        assert any(n.uid == "crates:package:mycrate" and n.kind == "contract" for n in r.nodes)
        assert any(e.edge_type == "declares" for e in r.edges)

    def test_all_dependency_sections(self):
        r = _extract(
            """
            [package]
            name = "c"
            [dependencies]
            serde = "1.0"
            [dev-dependencies]
            criterion = "0.5"
            [build-dependencies]
            cc = "1.0"
            """,
            path="Cargo.toml",
        )
        targets = {e.target_uid for e in r.edges if e.edge_type == "imports"}
        assert {
            "crates:package:serde",
            "crates:package:criterion",
            "crates:package:cc",
        } <= targets

    def test_workspace_concrete_member(self):
        r = _extract('[workspace]\nmembers = ["crates/core"]\n', path="repo/Cargo.toml")
        assert any(
            e.edge_type == "contains" and e.target_uid == "folder:repo/crates/core" for e in r.edges
        )

    def test_workspace_glob_member(self):
        r = _extract('[workspace]\nmembers = ["crates/*"]\n', path="repo/Cargo.toml")
        assert any(
            e.edge_type == "contains" and e.target_uid == "folder:repo/crates" for e in r.edges
        )


# ---------------------------------------------------------------------------
# Determinism + backend round-trip
# ---------------------------------------------------------------------------


class TestInvariants:
    _SRC = '[project]\nname = "app"\ndependencies = ["click>=8"]\n'

    def test_deterministic(self):
        a = code_toml.extract("pyproject.toml", self._SRC)
        b = code_toml.extract("pyproject.toml", self._SRC)
        assert [n.uid for n in a.nodes] == [n.uid for n in b.nodes]

    def test_backend_round_trip(self, migrated_conn):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        r = code_toml.extract("pyproject.toml", self._SRC)
        n, e = backend.bulk_upsert(r.nodes, r.edges)
        assert n == len(r.nodes)
