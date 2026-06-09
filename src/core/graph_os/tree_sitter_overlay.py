"""Tree-sitter overlay.

DEPENDS:  tree-sitter >= 0.22, tree-sitter-python, tree-sitter-typescript,
          tree-sitter-bash, tree-sitter-yaml (graph_os extra).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("graph_os.tree_sitter_overlay")


@dataclass(frozen=True)
class OverlayParse:
    """Wrapper around a tree-sitter parse result."""

    language_id: str
    tree: Any
    root: Any


def is_available() -> bool:
    """Return True iff the tree-sitter core package is importable."""
    try:
        import tree_sitter  # noqa: F401

        return True
    except ImportError:
        return False


@functools.lru_cache(maxsize=32)
def _load_language(language_id: str) -> Any | None:
    """Return a `tree_sitter.Language` for `language_id`, or None on miss.

    Language ids match the tree-sitter ecosystem (`python`, `typescript`,
    `tsx`, `bash`, `yaml`). Unknown ids return None so callers degrade.
    """
    if not is_available():
        return None
    try:
        from tree_sitter import Language
    except ImportError as exc:
        logger.debug("tree-sitter core missing: %s", exc)
        return None
    loader: Callable[[], Any] | None = _LOADERS.get(language_id)
    if loader is None:
        return None
    try:
        raw = loader()
    except ImportError as exc:
        logger.debug("grammar %s not installed: %s", language_id, exc)
        return None
    except Exception as exc:
        logger.debug("grammar %s failed to load: %s", language_id, exc)
        return None
    try:
        return Language(raw)
    except Exception as exc:
        logger.debug("Language wrap failed for %s: %s", language_id, exc)
        return None


def _load_python() -> Any:
    import tree_sitter_python as m

    return m.language()


def _load_typescript() -> Any:
    import tree_sitter_typescript as m

    return m.language_typescript()


def _load_tsx() -> Any:
    import tree_sitter_typescript as m

    return m.language_tsx()


def _load_bash() -> Any:
    import tree_sitter_bash as m

    return m.language()


def _load_yaml() -> Any:
    import tree_sitter_yaml as m

    return m.language()


def _load_go() -> Any:
    import tree_sitter_go as m

    return m.language()


# Polyglot baseline grammars (code_generic). Each is optional: a missing
# package makes _load_language return None and the generic extractor degrades
# to a file-node-only result with a dep_missing parse error.
def _load_rust() -> Any:
    import tree_sitter_rust as m

    return m.language()


def _load_ruby() -> Any:
    import tree_sitter_ruby as m

    return m.language()


def _load_java() -> Any:
    import tree_sitter_java as m

    return m.language()


def _load_c() -> Any:
    import tree_sitter_c as m

    return m.language()


def _load_cpp() -> Any:
    import tree_sitter_cpp as m

    return m.language()


def _load_c_sharp() -> Any:
    import tree_sitter_c_sharp as m

    return m.language()


_LOADERS: dict[str, Callable[[], Any]] = {
    "python": _load_python,
    "typescript": _load_typescript,
    "tsx": _load_tsx,
    "bash": _load_bash,
    "yaml": _load_yaml,
    "go": _load_go,
    "rust": _load_rust,
    "ruby": _load_ruby,
    "java": _load_java,
    "c": _load_c,
    "cpp": _load_cpp,
    "c_sharp": _load_c_sharp,
}


def parse(language_id: str, content: str) -> OverlayParse | None:
    """Parse `content` under `language_id`. Returns None when unavailable."""
    language = _load_language(language_id)
    if language is None:
        return None
    try:
        from tree_sitter import Parser
    except ImportError:
        return None
    try:
        parser = Parser(language)
    except TypeError:
        # Older tree-sitter (<0.22) used `Parser().set_language(...)`.
        try:
            parser = Parser()
            parser.set_language(language)
        except Exception as exc:
            logger.debug("parser init failed for %s: %s", language_id, exc)
            return None
    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception as exc:
        logger.debug("parse failed for %s: %s", language_id, exc)
        return None
    return OverlayParse(language_id=language_id, tree=tree, root=tree.root_node)


def iter_nodes(root: Any, kinds: set[str]):
    """Pre-order iterator yielding nodes whose `type` is in `kinds`."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in kinds:
            yield node
        # Reverse so traversal order matches source order after pop.
        stack.extend(reversed(list(node.children)))


def node_text(node: Any, content: bytes) -> str:
    """Return the source text covered by `node`."""
    try:
        start = node.start_byte
        end = node.end_byte
        return content[start:end].decode("utf-8", errors="replace")
    except Exception:
        return ""


__all__ = [
    "OverlayParse",
    "is_available",
    "iter_nodes",
    "node_text",
    "parse",
]
