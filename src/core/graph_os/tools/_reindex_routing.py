"""Suffix → (chain key, extractor list) routing for the auto-reindex dispatcher."""

from __future__ import annotations

import os

_EXT_MAP = {
    ".py": ("python", ["code_python", "contracts"]),
    ".ts": ("ts", ["code_ts", "contracts"]),
    ".tsx": ("tsx", ["code_ts", "contracts"]),
    ".sh": ("shell", ["code_shell"]),
    ".yaml": ("yaml", ["code_yaml"]),
    ".yml": ("yaml", ["code_yaml"]),
    ".go": ("go", ["code_go", "contracts"]),
    ".php": ("php", ["code_php", "contracts"]),
    ".json": ("json", ["code_json"]),
    ".toml": ("toml", ["code_toml"]),
    # Plain JavaScript routes through the TS extractor (JS is a syntactic
    # subset; the regex/tree-sitter passes degrade cleanly on .js).
    ".js": ("js", ["code_ts", "contracts"]),
    ".jsx": ("jsx", ["code_ts", "contracts"]),
    ".mjs": ("js", ["code_ts", "contracts"]),
    ".cjs": ("js", ["code_ts", "contracts"]),
    # Polyglot baseline via the table-driven code_generic extractor. These
    # extensions have no hand-written extractor; code_generic emits the
    # file + folder spine + function/class nodes for any language whose
    # grammar is installed (rust/ruby ship; others are code-ready). Hand-
    # written extractors above always win — generic only owns these routes.
    ".rs": ("rust", ["code_generic"]),
    ".rb": ("ruby", ["code_generic"]),
    ".java": ("java", ["code_generic"]),
    ".c": ("c", ["code_generic"]),
    ".h": ("c", ["code_generic"]),
    ".cc": ("cpp", ["code_generic"]),
    ".cpp": ("cpp", ["code_generic"]),
    ".cxx": ("cpp", ["code_generic"]),
    ".hpp": ("cpp", ["code_generic"]),
    ".hh": ("cpp", ["code_generic"]),
    ".cs": ("c_sharp", ["code_generic"]),
    ".scala": ("scala", ["code_generic"]),
    ".kt": ("kotlin", ["code_generic"]),
    ".kts": ("kotlin", ["code_generic"]),
    ".lua": ("lua", ["code_generic"]),
}

# Sentinel chain key stored on file_index_state for docs-only rows
# (markdown files that pass through the RAG indexer). Keeping it
# namespaced (``docs:md``) avoids collisions with any real extractor
# chain name.
_DOCS_CHAIN_KEY = "docs:md"


def _is_retryable_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


# Task-file path matcher. Comma-separated path fragments, env-overridable
# so projects that keep tickets under e.g. `docs/tickets/` or `tasks/`
# can opt into task_deps without forking the dispatcher. Each fragment
# is a substring match against the forward-slash-normalised repo-
# relative path.
_DEFAULT_TASK_PATH_FRAGMENTS = ("/tasks/", "docs/tasks/")


def _is_task_path(rel: str) -> bool:
    needle = rel.replace("\\", "/")
    raw = os.environ.get("COS_TASK_PATH_FRAGMENTS", "").strip()
    fragments: tuple[str, ...]
    if raw:
        fragments = tuple(p.strip() for p in raw.split(",") if p.strip())
    else:
        fragments = _DEFAULT_TASK_PATH_FRAGMENTS
    return any(frag in needle for frag in fragments)
