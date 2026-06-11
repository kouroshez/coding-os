"""Tests for graph_os.extractors.code_shell — regex fallback + path resolver.

The tree-sitter path is exercised by the existing I.7 suite; this file
targets the genuinely-uncovered code: the regex fallback walker (used on
lean installs without tree-sitter-bash) and the pure
``_resolve_script_target`` resolver branches.
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_shell


@pytest.fixture
def regex_mode(monkeypatch):
    # Force the regex fallback path (lean install without tree-sitter-bash).
    monkeypatch.setattr(code_shell, "_TS_AVAILABLE", False)


def _extract(src: str, *, path: str = "src/core/hooks/sample.sh"):
    return code_shell.extract(path, textwrap.dedent(src).lstrip("\n"))


# ---------------------------------------------------------------------------
# _resolve_script_target — pure resolver
# ---------------------------------------------------------------------------


class TestResolveScriptTarget:
    def test_empty_target(self):
        assert code_shell._resolve_script_target("a/b/x.sh", "") == ""

    def test_dirname_self_idiom_rewrites_to_sibling(self):
        out = code_shell._resolve_script_target("a/b/x.sh", '$(dirname "$0")/helper.sh')
        assert out == "code:file:a/b/helper.sh"

    def test_dirname_bash_source_idiom(self):
        # Resolver handles the unbraced $BASH_SOURCE[0] form.
        out = code_shell._resolve_script_target("a/b/x.sh", '$(dirname "$BASH_SOURCE[0]")/lib.sh')
        assert out == "code:file:a/b/lib.sh"

    def test_dirname_braced_bash_source_idiom(self):
        # Braced ${BASH_SOURCE[0]} — the common real-world form (was lost).
        out = code_shell._resolve_script_target("a/b/x.sh", '$(dirname "${BASH_SOURCE[0]}")/lib.sh')
        assert out == "code:file:a/b/lib.sh"

    def test_dirname_braced_zero(self):
        out = code_shell._resolve_script_target("a/b/x.sh", '$(dirname "${0}")/lib.sh')
        assert out == "code:file:a/b/lib.sh"

    def test_still_dynamic_var_returns_empty(self):
        assert code_shell._resolve_script_target("a/b/x.sh", "$HOME/x.sh") == ""

    def test_backtick_dynamic_returns_empty(self):
        assert code_shell._resolve_script_target("a/b/x.sh", "`pwd`/x.sh") == ""

    def test_absolute_path(self):
        assert (
            code_shell._resolve_script_target("a/b/x.sh", "/opt/tools/y.sh")
            == "code:file:opt/tools/y.sh"
        )

    def test_relative_parent_traversal(self):
        assert (
            code_shell._resolve_script_target("a/b/x.sh", "../helper.sh") == "code:file:a/helper.sh"
        )

    def test_relative_sibling_dot_slash(self):
        assert (
            code_shell._resolve_script_target("a/b/x.sh", "./helper.sh")
            == "code:file:a/b/helper.sh"
        )


# ---------------------------------------------------------------------------
# Regex fallback walker
# ---------------------------------------------------------------------------


class TestRegexFallback:
    def test_file_module_contains_always(self, regex_mode):
        r = _extract("echo hi")
        assert any(n.kind == "code:file" for n in r.nodes)
        assert any(n.kind == "code:module" for n in r.nodes)
        assert any(e.edge_type == "contains" for e in r.edges)

    def test_function_def_emitted(self, regex_mode):
        r = _extract(
            """
            my_func() {
              echo hi
            }
            """
        )
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "my_func" for n in fns)

    def test_function_keyword_form(self, regex_mode):
        r = _extract("function setup() {\n  :\n}\n")
        assert any(n.label == "setup" for n in r.nodes if n.kind == "code:function")

    def test_source_emits_imports(self, regex_mode):
        r = _extract("source ./cos-env.sh\n")
        assert any(e.edge_type == "imports" for e in r.edges)

    def test_dot_source_form(self, regex_mode):
        r = _extract(". ./cos-env.sh\n")
        assert any(e.edge_type == "imports" for e in r.edges)

    def test_dynamic_source_is_not_a_parse_error(self, regex_mode):
        # TASK-303: a `source "$VAR/x.sh"` is parsed fine but unresolvable —
        # it must NOT be recorded as a parse error (was inflating shell counts).
        r = _extract('source "$HOOK_DIR/cos-env.sh"\n')
        assert r.parse_errors == []
        assert not any(e.edge_type == "imports" for e in r.edges)

    def test_call_script_emits_calls(self, regex_mode):
        r = _extract("bash scripts/deploy.sh\n", path="src/core/hooks/x.sh")
        assert any(e.edge_type == "calls" for e in r.edges)

    def test_cos_log_hook_handles_tool(self, regex_mode):
        r = _extract("cos_log_hook my-hook enter\n")
        assert any(
            e.edge_type == "handles_tool" and e.target_uid == "cos:hook:my-hook" for e in r.edges
        )

    def test_heredoc_function_not_matched(self, regex_mode):
        # E10: a function-looking line INSIDE a heredoc must not spawn a node.
        r = _extract(
            """
            cat <<EOF
            phantom_func() {
              echo nope
            }
            EOF
            """
        )
        assert not any(n.label == "phantom_func" for n in r.nodes if n.kind == "code:function")

    def test_commented_function_not_matched(self, regex_mode):
        r = _extract("# ghost() {\nreal() {\n  :\n}\n")
        labels = {n.label for n in r.nodes if n.kind == "code:function"}
        assert "ghost" not in labels and "real" in labels

    def test_self_call_skipped(self, regex_mode):
        # Calling own basename (no slash) must not emit a self calls-edge.
        r = _extract("bash sample.sh\n", path="src/core/hooks/sample.sh")
        assert not any(
            e.edge_type == "calls" and e.target_uid.endswith("sample.sh") for e in r.edges
        )

    def test_dynamic_source_is_not_a_parse_error(self, regex_mode):
        # TASK-303: an unresolvable dynamic source is expected, not a parse
        # error (was kind="dynamic" in parse_errors, inflating shell counts).
        r = _extract("source $SOME_DIR/x.sh\n")
        assert not any(pe.kind == "dynamic" for pe in r.parse_errors)

    def test_local_function_call_edge(self, regex_mode):
        # Parity with the tree-sitter path: a same-file function invoked as
        # a command emits a `calls` edge (regex fallback used to miss this).
        r = _extract("helper() {\n  echo hi\n}\nmain() {\n  helper\n}\n")
        assert any(e.edge_type == "calls" and e.target_uid.endswith("::helper") for e in r.edges)

    def test_local_call_forward_reference(self, regex_mode):
        # Function called before it is defined (collected in a pre-pass).
        r = _extract("main() {\n  later\n}\nlater() {\n  :\n}\n")
        assert any(e.edge_type == "calls" and e.target_uid.endswith("::later") for e in r.edges)

    def test_non_local_command_no_call_edge(self, regex_mode):
        # `ls` is not a same-file function → no spurious calls edge.
        r = _extract("main() {\n  ls -la\n}\n")
        assert not any(e.edge_type == "calls" for e in r.edges)

    def test_definition_line_is_not_a_self_call(self, regex_mode):
        # A lone function definition must not emit a calls edge to itself.
        r = _extract("solo() {\n  echo x\n}\n")
        assert not any(e.edge_type == "calls" for e in r.edges)


# ---------------------------------------------------------------------------
# Determinism (regex path)
# ---------------------------------------------------------------------------


class TestDeterminism:
    _SRC = "source ./cos-env.sh\nmy_fn() {\n  cos_log_hook h enter\n}\n"

    def test_regex_deterministic(self, regex_mode):
        a = code_shell.extract("src/core/hooks/x.sh", self._SRC)
        b = code_shell.extract("src/core/hooks/x.sh", self._SRC)
        assert [n.uid for n in a.nodes] == [n.uid for n in b.nodes]
        assert [(e.source_uid, e.target_uid, e.edge_type) for e in a.edges] == [
            (e.source_uid, e.target_uid, e.edge_type) for e in b.edges
        ]


# ---------------------------------------------------------------------------
# tree-sitter grammar gaps vs real parse errors (roadmap §6, TASK-395)
# ---------------------------------------------------------------------------


class TestGrammarGapReclassification:
    def test_valid_bash_grammar_gap_not_a_parse_error(self):
        if not code_shell._TS_AVAILABLE:
            pytest.skip("tree-sitter-bash not installed")
        # `$((10#$x))` is valid bash that tree-sitter-bash cannot parse.
        src = (
            "#!/usr/bin/env bash\n"
            "calc() {\n"
            "  local t0_us=$((10#$1 * 1000000 + 10#$2))\n"
            "  echo \"$t0_us\"\n"
            "}\n"
        )
        r = code_shell.extract("src/core/hooks/gap.sh", src)
        assert r.parse_errors == []
        mod = next(n for n in r.nodes if n.uid.startswith("code:module:"))
        assert mod.metadata.get("grammar_gaps", 0) >= 1

    def test_real_syntax_error_still_counts(self):
        if not code_shell._TS_AVAILABLE:
            pytest.skip("tree-sitter-bash not installed")
        src = "#!/usr/bin/env bash\nif [ ; then fi(((\n"
        r = code_shell.extract("src/core/hooks/broken.sh", src)
        assert any(p.kind == "tree_sitter_error" for p in r.parse_errors)

    def test_bash_syntax_ok_helper(self):
        assert code_shell._bash_syntax_ok("echo hi\n")
        assert not code_shell._bash_syntax_ok("if [ ; then fi(((\n")
