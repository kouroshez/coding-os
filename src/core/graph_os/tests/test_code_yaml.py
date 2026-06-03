"""Tests for graph_os.extractors.code_yaml — YAML extractor edge cases.

Targets the genuinely-uncovered branches: hook-registry first-class
emission, reference-key edge typing, _classify_target target shapes,
and the parse-error / empty / top-level-list paths.
"""

from __future__ import annotations

import textwrap

from graph_os.extractors import code_yaml


def _extract(src: str, *, path: str = "config/sample.yaml"):
    return code_yaml.extract(path, textwrap.dedent(src).lstrip("\n"))


# ---------------------------------------------------------------------------
# File + module spine
# ---------------------------------------------------------------------------


class TestFileModule:
    def test_file_and_module_and_contains(self):
        r = _extract("name: x")
        files = [n for n in r.nodes if n.kind == "code:file"]
        mods = [n for n in r.nodes if n.kind == "code:module"]
        assert len(files) == 1 and len(mods) == 1
        assert files[0].lang == "yaml"
        assert any(
            e.edge_type == "contains" and e.target_uid == mods[0].uid for e in r.edges
        )

    def test_empty_document_no_crash(self):
        # `data is None` branch — file/module still emitted, no parse error.
        r = _extract("")
        assert any(n.kind == "code:file" for n in r.nodes)
        assert r.parse_errors == []

    def test_malformed_yaml_records_parse_error(self):
        r = _extract("key: [unclosed\n  : :")
        assert any(pe.kind == "yaml_parse_error" for pe in r.parse_errors)
        # File node still present despite the parse failure.
        assert any(n.kind == "code:file" for n in r.nodes)

    def test_top_level_list(self):
        r = _extract(
            """
            - one
            - two
            """
        )
        assert any(n.kind == "code:file" for n in r.nodes)


# ---------------------------------------------------------------------------
# Hook registry (registry.yaml shape) — first-class cos:hook nodes
# ---------------------------------------------------------------------------


class TestHookRegistry:
    _REG = """
    hooks:
      - id: my-hook
        script: my-hook.sh
        category: safety
        phase: gate
      - id: nested-hook
        script: sub/dir/nested.sh
    """

    def test_emits_hook_nodes(self):
        r = _extract(self._REG, path="src/core/hooks/registry.yaml")
        hook_nodes = [n for n in r.nodes if n.kind == "hook"]
        labels = {n.label for n in hook_nodes}
        assert {"my-hook", "nested-hook"} <= labels

    def test_hook_contains_edge_from_file(self):
        r = _extract(self._REG, path="src/core/hooks/registry.yaml")
        assert any(
            e.edge_type == "contains" and e.target_uid == "cos:hook:my-hook"
            for e in r.edges
        )

    def test_hook_declares_script_with_slash_kept_verbatim(self):
        r = _extract(self._REG, path="src/core/hooks/registry.yaml")
        # script "sub/dir/nested.sh" has a slash → kept as-is (raw path).
        assert any(
            e.edge_type == "declares"
            and e.target_uid == "code:file:sub/dir/nested.sh"
            for e in r.edges
        )

    def test_hook_declares_bare_script_falls_back_to_raw(self):
        # Bare "my-hook.sh" resolved against registry dir; the file does not
        # exist on disk during the test → falls back to the raw name.
        r = _extract(self._REG, path="src/core/hooks/registry.yaml")
        assert any(
            e.edge_type == "declares" and e.target_uid.endswith("my-hook.sh")
            for e in r.edges
        )

    def test_non_dict_entry_skipped(self):
        r = _extract(
            """
            hooks:
              - just-a-string
              - id: real
                script: real.sh
            """,
            path="src/core/hooks/registry.yaml",
        )
        hook_nodes = [n for n in r.nodes if n.kind == "hook"]
        assert {n.label for n in hook_nodes} == {"real"}

    def test_entry_missing_id_skipped(self):
        r = _extract(
            """
            hooks:
              - script: orphan.sh
              - id: ok
                script: ok.sh
            """,
            path="src/core/hooks/registry.yaml",
        )
        assert {n.label for n in r.nodes if n.kind == "hook"} == {"ok"}


# ---------------------------------------------------------------------------
# Reference keys → typed edges
# ---------------------------------------------------------------------------


class TestReferenceKeys:
    def test_read_first_emits_references_doc(self):
        r = _extract("read_first:\n  - docs/spec.md")
        assert any(
            e.edge_type == "references_doc"
            and e.target_uid == "doc:file:docs/spec.md"
            for e in r.edges
        )

    def test_includes_emits_imports(self):
        r = _extract("includes:\n  - shared/base.yaml")
        assert any(
            e.edge_type == "imports"
            and e.target_uid == "code:file:shared/base.yaml"
            for e in r.edges
        )

    def test_ssot_boolean_flag_emits_no_pointer_edge(self):
        # `ssot: true` maps to edge_type None → no reference edge.
        r = _extract("ssot: true")
        assert not any(e.edge_type in ("ssot_of", "references_doc") for e in r.edges)

    def test_non_path_values_skip_reference_emission(self):
        # `rules: [allow_label]` — no value looks path-shaped → no phantom edge.
        r = _extract("rules:\n  - allow_pr_label\n  - require_review")
        assert not any(e.edge_type == "references_doc" for e in r.edges)

    def test_references_key_external_url(self):
        r = _extract("references:\n  - https://example.com/doc")
        assert any(
            e.target_uid == "doc:external:https://example.com/doc" for e in r.edges
        )


# ---------------------------------------------------------------------------
# _classify_target — every target shape
# ---------------------------------------------------------------------------


class TestClassifyTarget:
    def test_empty_is_none(self):
        assert code_yaml._classify_target("   ") is None

    def test_http_external(self):
        assert code_yaml._classify_target("https://x.io/a").startswith("doc:external:")

    def test_md_is_doc_file(self):
        assert code_yaml._classify_target("docs/a.md") == "doc:file:docs/a.md"

    def test_sh_is_code_file(self):
        assert code_yaml._classify_target("x/a.sh") == "code:file:x/a.sh"

    def test_yaml_is_code_file(self):
        assert code_yaml._classify_target("a.yaml") == "code:file:a.yaml"

    def test_py_is_code_file(self):
        assert code_yaml._classify_target("pkg/m.py") == "code:file:pkg/m.py"

    def test_slash_path_is_code_file(self):
        assert code_yaml._classify_target("some/dir/thing") == "code:file:some/dir/thing"

    def test_bare_name_is_identifier(self):
        assert code_yaml._classify_target("clean-code") == "cos:identifier:clean-code"


# ---------------------------------------------------------------------------
# Scalar + target helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_stringify_scalar_primitives(self):
        assert code_yaml._stringify_scalar("a") == "a"
        assert code_yaml._stringify_scalar(3) == "3"
        assert code_yaml._stringify_scalar(True) == "True"

    def test_stringify_scalar_none_is_empty(self):
        assert code_yaml._stringify_scalar(None) == ""

    def test_stringify_scalar_container_is_typename(self):
        assert code_yaml._stringify_scalar([1, 2]) == "list"
        assert code_yaml._stringify_scalar({"a": 1}) == "dict"

    def test_iter_targets_str(self):
        assert code_yaml._iter_targets("a") == ["a"]

    def test_iter_targets_list_filters_non_str(self):
        assert code_yaml._iter_targets(["a", 1, "b", None]) == ["a", "b"]

    def test_iter_targets_other_is_empty(self):
        assert code_yaml._iter_targets(42) == []


# ---------------------------------------------------------------------------
# Determinism + backend round-trip
# ---------------------------------------------------------------------------


class TestInvariants:
    _SRC = "read_first:\n  - docs/a.md\nhooks:\n  - id: h\n    script: h.sh\n"

    def test_deterministic(self):
        a = code_yaml.extract("config/x.yaml", self._SRC)
        b = code_yaml.extract("config/x.yaml", self._SRC)
        assert [n.uid for n in a.nodes] == [n.uid for n in b.nodes]
        assert [(e.source_uid, e.target_uid, e.edge_type) for e in a.edges] == [
            (e.source_uid, e.target_uid, e.edge_type) for e in b.edges
        ]

    def test_backend_round_trip(self, migrated_conn):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        r = code_yaml.extract("config/x.yaml", self._SRC)
        n, e = backend.bulk_upsert(r.nodes, r.edges)
        assert n == len(r.nodes)
        assert e == len(r.edges)
