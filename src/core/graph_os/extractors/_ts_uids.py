"""uid grammar and language constants for the TypeScript / TSX extractor.

Leaf module: imports nothing from its siblings, so both the tree-sitter walk
and the regex fallback can depend on it without the import cycle that forced
the old bottom-of-file import in code_ts.py.
"""

from __future__ import annotations

from .md_links import _normalize_path

EXTRACTOR_ID = "code_ts@v1"
# tree-sitter primary path for TS/TSX. Activated by
# COS_EXTRACTOR_PREFERENCE=tree-sitter when the grammar is installed.
EXTRACTOR_ID_TS = "code_ts_ts@v1"

_TS_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "return",
        "new",
        "catch",
        "function",
        "typeof",
        "await",
        "import",
        "export",
        "throw",
        "yield",
    }
)


def _tree_sitter_ts_active(lang_id: str) -> bool:
    """True when imports / heritage should be tagged as tree-sitter.

    Activation conditions:
      - COS_EXTRACTOR_PREFERENCE == "tree-sitter"
      - the requested language grammar (typescript / tsx) is loadable

    Default `auto` mode keeps the legacy regex tag so existing graphs
    don't double-emit during rollout.
    """
    import os as _os

    pref = (_os.environ.get("COS_EXTRACTOR_PREFERENCE") or "auto").lower()
    if pref != "tree-sitter":
        return False
    try:
        from ..tree_sitter_overlay import _load_language

        return _load_language(lang_id) is not None
    except Exception:
        return False


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    # TS modules identify by file path — no package system by default.
    return f"code:module:{_normalize_path(path)}"


def class_uid(path: str, name: str) -> str:
    return f"code:class:{_normalize_path(path)}::{name}"


def interface_uid(path: str, name: str) -> str:
    return f"code:interface:{_normalize_path(path)}::{name}"


def function_uid(path: str, name: str) -> str:
    return f"code:function:{_normalize_path(path)}::{name}"


def _ts_method_uid(path: str, cls: str, name: str) -> str:
    return f"code:method:{path}::{cls}.{name}"
