"""AST-accurate symbol and edge walk over a parsed TypeScript / TSX tree.

The parity path: emits the same node/edge shapes as the regex fallback but
scope-accurate — calls sourced at the enclosing function/method, heritage and
type annotations resolved against the file's complete local symbol table. The
declaration pass must run first; it is what fills `local_names`.
"""

from __future__ import annotations

from typing import Any

from ._ts_calls import _walk_ts_calls
from ._ts_decls import _walk_ts_declarations
from .md_links import ExtractionResult


def _walk_ts_symbols(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    file_uid_: str,
    lang: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """AST-accurate symbol/edge extraction from a tree-sitter TS/TSX tree."""
    methods_by_class = _walk_ts_declarations(
        root,
        path=path,
        module_uid_=module_uid_,
        lang=lang,
        imported_names=imported_names,
        local_names=local_names,
        result=result,
    )
    _walk_ts_calls(
        root,
        path=path,
        module_uid_=module_uid_,
        lang=lang,
        imported_names=imported_names,
        local_names=local_names,
        methods_by_class=methods_by_class,
        result=result,
    )
