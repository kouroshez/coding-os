"""Suffix → (chain key, extractor list) routing for the auto-reindex dispatcher."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from graph_os.ingest.base import is_shell_script
from graph_os.resolve_ts import config_inputs

_EXT_MAP = {
    ".py": ("python", ["code_python", "contracts"]),
    ".ts": ("ts", ["code_ts", "contracts"]),
    ".tsx": ("tsx", ["code_ts", "contracts"]),
    ".mts": ("ts", ["code_ts", "contracts"]),
    ".cts": ("ts", ["code_ts", "contracts"]),
    # Astro: code_ts reads a same-length mask of the frontmatter and scripts.
    ".astro": ("astro", ["code_ts", "contracts"]),
    ".sh": ("shell", ["code_shell"]),
    ".bash": ("shell", ["code_shell"]),
    ".zsh": ("shell", ["code_shell"]),
    ".yaml": ("yaml", ["code_yaml"]),
    ".yml": ("yaml", ["code_yaml"]),
    ".go": ("go", ["code_go", "contracts"]),
    # go.mod; code_gomod leaves any other `.mod` file a bare node.
    ".mod": ("gomod", ["code_gomod"]),
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

# The per-file cache matches content hash and chain key, so an extractor upgrade
# never reaches a file nobody edited: bump this whenever extraction output
# changes for unchanged input, and the next reindex re-reads every file once.
GRAPH_EXTRACTION_VERSION = 57


def versioned_chain_key(chain: list[str], fingerprint: str = "") -> str:
    key = f"{','.join(chain)}#{GRAPH_EXTRACTION_VERSION}"
    return f"{key}#{fingerprint}" if fingerprint else key


_TS_FAMILY = frozenset({"ts", "tsx", "js", "jsx", "astro"})


def resolution_fingerprint(project_root: Path, rel: str, language: str) -> str:
    """Digest of the config a file's imports resolve through: a tsconfig `paths` or go.mod edit re-reads it."""
    directory = PurePosixPath(rel).parent.as_posix()
    if language in _TS_FAMILY:
        inputs = config_inputs(project_root, directory)
    elif language == "go":
        inputs = _go_config_inputs(project_root, directory)
    else:
        return ""
    digest = hashlib.sha256()
    for name in inputs:
        path = project_root / name
        digest.update(name.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"")
    return digest.hexdigest()[:12]


def _go_config_inputs(project_root: Path, directory: str) -> list[str]:
    inputs: list[str] = []
    current: str | None = directory
    while current is not None:
        prefix = "" if current in ("", ".") else f"{current}/"
        if (
            not any(name.endswith("go.mod") for name in inputs)
            and (project_root / f"{prefix}go.mod").is_file()
        ):
            inputs.append(f"{prefix}go.mod")
        if (project_root / f"{prefix}go.work").is_file():
            inputs.append(f"{prefix}go.work")
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return inputs


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


def graph_chain_for(file_path: Path, rel: str) -> tuple[str, list[str]] | None:
    suffix = file_path.suffix.lower()
    if suffix in _EXT_MAP:
        return _EXT_MAP[suffix]
    if not suffix and is_shell_script(file_path):
        return ("shell", ["code_shell"])
    if suffix not in (".md", ".mdx"):
        return None
    if _is_task_path(rel):
        return ("markdown-task", ["task_deps", "md_links"])
    # A Markdown file under an Astro site's src/pages/ is a page, a route.
    if "/src/pages/" in f"/{rel}":
        return ("markdown", ["md_links", "contracts"])
    return ("markdown", ["md_links"])
