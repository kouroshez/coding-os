"""An `.astro` client script is its own module: own scope, read only when Astro processes it."""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_typescript")

PATH = "src/components/Dual.astro"


def _extract(text: str):
    from graph_os.extractors import code_ts

    return code_ts.extract(PATH, text)


def _module_imports(result) -> set[str]:
    return {
        edge.target_uid
        for edge in result.edges
        if edge.edge_type == "imports" and edge.source_uid == f"code:module:{PATH}"
    }


def test_a_client_script_keeps_its_own_scope():
    result = _extract(
        "---\n"
        "import { en } from '../i18n/en';\n"
        "function label() { return en.title; }\n"
        "---\n"
        "<h1>{label()}</h1>\n"
        "<script>\n"
        "  import { en } from '../i18n/client-en';\n"
        "  function label() { return en.short; }\n"
        "  document.title = label();\n"
        "</script>\n"
    )
    uids = [node.uid for node in result.nodes]
    calls = {
        (edge.source_span, edge.target_uid) for edge in result.edges if edge.edge_type == "calls"
    }

    assert len(uids) == len(set(uids))
    assert {f"code:import:{PATH}::en", f"code:import:{PATH}::script.en"} <= set(uids)
    assert {f"code:function:{PATH}::label", f"code:function:{PATH}::script.label"} <= set(uids)
    assert (f"{PATH}:5", f"code:function:{PATH}::label") in calls
    assert (f"{PATH}:9", f"code:function:{PATH}::script.label") in calls
    assert (f"{PATH}:9", f"code:function:{PATH}::label") not in calls


def test_only_a_script_astro_processes_is_read_and_a_src_script_is_an_import():
    result = _extract(
        "---\n---\n"
        "<script>\nimport { a } from './a';\na();\n</script>\n"
        "<script type=\"module\">\nimport { b } from './b';\n</script>\n"
        "<script is:inline>\nimport { c } from './c';\n</script>\n"
        "<script data-astro-rerun>\nimport { d } from './d';\n</script>\n"
        '<script src="../scripts/menu.ts"></script>\n'
        '<script is:inline src="/vendor/analytics.js"></script>\n'
    )

    assert _module_imports(result) == {
        "code:module:src/components/a.ts",
        "code:module:src/scripts/menu.ts",
    }


def test_a_fence_inside_a_string_and_a_byte_order_mark_keep_the_frontmatter_whole():
    in_string = _extract(
        "---\n"
        "import A from './A.astro';\n"
        "const md = `\n---\n`;\n"
        "import B from './B.astro';\n"
        "function late() { return 1; }\n"
        "---\n"
        "<A /><B />\n"
    )
    with_bom = _extract("﻿---\nimport A from './A.astro';\n---\n<A />\n")

    assert _module_imports(in_string) == {
        "code:module:src/components/A.astro",
        "code:module:src/components/B.astro",
    }
    assert f"code:function:{PATH}::late" in {node.uid for node in in_string.nodes}
    assert _module_imports(with_bom) == {"code:module:src/components/A.astro"}
