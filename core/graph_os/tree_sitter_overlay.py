"""Tree-sitter overlay (Phase I.4b / I.6b).

PURPOSE:  Wrap the pinned `tree-sitter` Python bindings + per-language
          grammar packages (python, typescript, bash, yaml) in a
          single cached registry. Gives extractors a reliable AST
          without each one re-importing grammars.
INPUT:    language id + raw content.
OUTPUT:   `OverlayParse(tree, root, language_id)` — or None when the
          grammar isn't installed.
DEPENDS:  tree-sitter >= 0.22, tree-sitter-python, tree-sitter-typescript,
          tree-sitter-bash, tree-sitter-yaml (graph-os extra).
NOTES:    Fallback-safe: if a grammar import fails, callers see None
          and stay on their ast / regex baseline — zero crash.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from typing import Any, Callable

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


@functools.lru_cache(maxsize=8)
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
    except Exception as exc:  # noqa: BLE001
        logger.debug("grammar %s failed to load: %s", language_id, exc)
        return None
    try:
        return Language(raw)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Language wrap failed for %s: %s", language_id, exc)
        return None


def _load_python() -> Any:
    import tree_sitter_python as m  # noqa: WPS433

    return m.language()


def _load_typescript() -> Any:
    import tree_sitter_typescript as m  # noqa: WPS433

    return m.language_typescript()


def _load_tsx() -> Any:
    import tree_sitter_typescript as m  # noqa: WPS433

    return m.language_tsx()


def _load_bash() -> Any:
    import tree_sitter_bash as m  # noqa: WPS433

    return m.language()


def _load_yaml() -> Any:
    import tree_sitter_yaml as m  # noqa: WPS433

    return m.language()


_LOADERS: dict[str, Callable[[], Any]] = {
    "python": _load_python,
    "typescript": _load_typescript,
    "tsx": _load_tsx,
    "bash": _load_bash,
    "yaml": _load_yaml,
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
        except Exception as exc:  # noqa: BLE001
            logger.debug("parser init failed for %s: %s", language_id, exc)
            return None
    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        return ""


__all__ = [
    "OverlayParse",
    "is_available",
    "parse",
    "iter_nodes",
    "node_text",
]
