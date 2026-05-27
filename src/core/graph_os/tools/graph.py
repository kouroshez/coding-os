"""graph_os — the 11 cos_graph_* MCP tools (I.8).

DEPENDS:  graph_os.types, graph_os.backend, graph_os.backends.*.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
import sqlite3
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..backend import BackendUnavailable, GraphBackend, get_backend
from ..types import GraphEdge, GraphNode

logger = logging.getLogger("graph_os.tools.graph")


# ---------------------------------------------------------------------------
# Envelope helpers — shared with thinking_os via sys.path.
# ---------------------------------------------------------------------------


def _envelope_module():
    try:
        from tools import _shared  # type: ignore

        return _shared
    except ImportError:
        here = Path(__file__).resolve()
        candidate = here.parent.parent.parent / "thinking_os"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        from tools import _shared  # type: ignore

        return _shared


def _ok(data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    shared = _envelope_module()
    merged = {"layer": "graph", **(meta or {})}
    _emit_telemetry(meta=merged, ok=True)
    _touch_session_marker()
    return shared.ok(data, meta=merged)


def _touch_session_marker() -> None:
    """Record that a cos_graph_* call succeeded this agent session.

    Consumed by enforce-graph-first-read.sh — when the marker exists,
    the hook stays silent on Read. Fail-open: any error is logged at
    debug level only, never raises.
    """
    try:
        agent_dir = os.environ.get("COS_AGENT_DIR")
        if not agent_dir:
            state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
            agent = os.environ.get("COS_AGENT") or "claude"
            agent_dir = f"{state_dir}/{agent}"
        from pathlib import Path as _Path

        path = _Path(agent_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / ".graph-call-seen").touch(exist_ok=True)
    except OSError as exc:
        logger.debug("graph-call-seen marker failed: %s", exc)


def _fail(
    category: str,
    message: str,
    *,
    retryable: bool | None = None,
) -> dict[str, Any]:
    shared = _envelope_module()
    _emit_telemetry(
        meta={"layer": "graph", "category": category, "message": message},
        ok=False,
    )
    return shared.fail(category, message, retryable=retryable)


# G36: graph.py local validators wrap _fail so telemetry fires on
# validation failures too. _shared.py exposes the same helpers for
# board_os / thinking_os tools that don't need the telemetry layer.
def _validate_enum(value: Any, allowed: tuple[str, ...], field: str) -> Any:
    if value not in allowed:
        return _fail("validation", f"{field} must be one of {allowed} (got {value!r})")
    return None


def _validate_positive_int(value: Any, field: str) -> Any:
    if not isinstance(value, int) or value <= 0:
        return _fail("validation", f"{field} must be a positive int (got {value!r})")
    return None


def _validate_non_negative_int(value: Any, field: str) -> Any:
    if not isinstance(value, int) or value < 0:
        return _fail("validation", f"{field} must be >= 0 (got {value!r})")
    return None


def _validate_confidence(value: Any, field: str) -> Any:
    # W7.1 / R4-19/R4-26: confidence is in [0.0, 1.0]; impact + query
    # silently accepted 999 and filtered everything.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _fail("validation", f"{field} must be a number (got {type(value).__name__})")
    if value < 0.0 or value > 1.0:
        return _fail("validation", f"{field} must be in [0.0, 1.0] (got {value})")
    return None


def _validate_min_chars(value: Any, field: str, *, min_chars: int = 2) -> Any:
    # W7.1 / R4-09: cos_graph_query enforces 2-char min; cos_graph_resolve
    # silently accepted single-char fuzzy. Parity.
    if not isinstance(value, str):
        return _fail("validation", f"{field} must be a string (got {type(value).__name__})")
    if len(value.strip()) < min_chars:
        return _fail("validation", f"{field} must be at least {min_chars} chars")
    return None


def _clamp_int(value: int, *, min_v: int, max_v: int) -> tuple[int, bool]:
    clamped = max(min_v, min(int(value), max_v))
    return clamped, clamped != value


# -- Telemetry --------------------------------------------------------
# Append-only JSONL log of every cos_graph_* invocation. One line per
# call: {ts, ok, layer, source, backend, ...meta}. The file lives in
# $COS_STATE_DIR/.graph-telemetry.jsonl and is rotated when it crosses
# a soft cap so the disk footprint stays bounded.

_TELEMETRY_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_TELEMETRY_PATH_CACHE: list[str] = []


def _telemetry_path() -> str | None:
    if _TELEMETRY_PATH_CACHE:
        return _TELEMETRY_PATH_CACHE[0]
    state_dir = os.environ.get("COS_STATE_DIR")
    if not state_dir:
        # Fall back to repo-rooted .coding-os when env unset.
        from pathlib import Path as _Path

        state_dir = str(_Path.cwd() / ".coding-os")
    try:
        from pathlib import Path as _Path

        path = _Path(state_dir)
        path.mkdir(parents=True, exist_ok=True)
        full = str(path / ".graph-telemetry.jsonl")
        _TELEMETRY_PATH_CACHE.append(full)
        return full
    except OSError as exc:
        logger.debug("telemetry path setup failed: %s", exc)
        return None


def _rotate_telemetry_atomically(path: str) -> None:
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size <= _TELEMETRY_MAX_BYTES:
        return
    tmp = f"{path}.rotating"
    try:
        with open(path, "rb") as src:
            src.seek(size // 2)
            tail = src.read()
        with open(tmp, "wb") as dst:
            dst.write(tail)
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug("telemetry rotation skipped: %s", exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _emit_telemetry(*, meta: dict[str, Any], ok: bool) -> None:
    """Append one JSONL row. Fail-open — telemetry must never block a tool."""
    try:
        path = _telemetry_path()
        if path is None:
            return
        import json as _json
        import time as _time

        row = {
            "ts": int(_time.time()),
            "ok": ok,
            **{k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))},
        }
        line = _json.dumps(row, default=str) + "\n"
        _rotate_telemetry_atomically(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        logger.debug("telemetry emit suppressed: %s", exc)


# ---------------------------------------------------------------------------
# Backend handle — lazy, shared, re-openable.
# ---------------------------------------------------------------------------


# Legacy single-instance singleton — kept as a test-override seam.  Tests
# in core/graph_os/tests/ monkey-patch this directly to inject a stub
# backend; the new project-scoped dict below takes precedence ONLY when
# this legacy slot is None.  Production callers (MCP, Hub web) never
# write to `_BACKEND_SINGLETON` so the project-scoped path always wins.
_BACKEND_SINGLETON: GraphBackend | None = None
_BACKEND_SINGLETONS: dict[str, GraphBackend] = {}
_BACKEND_LOCK = threading.Lock()


def _current_db_key() -> str:
    """Resolve the SQLite DB path for the current project scope."""
    try:
        from thinking_os.database import resolve_db_path  # type: ignore

        return str(resolve_db_path())
    except Exception:
        return "__default__"


def _repo_root_for_paths() -> Path:
    """Project root used to resolve relative file_path entries against the
    filesystem (e.g. stale-path detection in cos_graph_doctor).

    The DB lives at ``<repo>/.coding-os/coding-os.db``, so we walk two
    parents up. Falls back to CWD if the DB path can't be resolved.
    """
    try:
        from thinking_os.database import resolve_db_path  # type: ignore

        db = Path(resolve_db_path()).resolve()
        return db.parent.parent
    except Exception:
        return Path.cwd().resolve()


def _backend(*, backend: str | None = None) -> GraphBackend:
    """Return the shared GraphBackend instance for the active project scope.

    Lookup order:
      1. ``_BACKEND_SINGLETON`` legacy slot — non-None only when a test
         has installed a stub backend via direct module-attr assignment.
      2. ``_BACKEND_SINGLETONS[db_path]`` — production path.  Keyed by
         resolved SQLite DB path so the Hub web layer can serve many
         projects from one process without one project leaking into
         another's response.  MCP / CLI callers see exactly one entry
         and behave as before.

    B7: close the previous backend before replacing the singleton when the
    caller asks for a different backend, so file handles / DB connections
    don't leak across the swap. Lock guards against concurrent callers
    swapping the singleton mid-call.
    """
    with _BACKEND_LOCK:
        if _BACKEND_SINGLETON is not None and backend is None:
            return _BACKEND_SINGLETON
        key = _current_db_key()
        existing = _BACKEND_SINGLETONS.get(key)
        if existing is None or backend is not None:
            if existing is not None:
                try:
                    existing.close()
                except Exception as exc:
                    logger.debug("previous backend close suppressed: %s", exc)
            new_backend = get_backend(backend=backend)
            _BACKEND_SINGLETONS[key] = new_backend
            return new_backend
        return existing


def reset_backend() -> None:
    """Test-only: drop both legacy + project-scoped caches."""
    global _BACKEND_SINGLETON
    with _BACKEND_LOCK:
        if _BACKEND_SINGLETON is not None:
            try:
                _BACKEND_SINGLETON.close()
            except Exception as exc:
                logger.debug("legacy backend close suppressed: %s", exc)
            _BACKEND_SINGLETON = None
        for bk in list(_BACKEND_SINGLETONS.values()):
            try:
                bk.close()
            except Exception as exc:
                logger.debug("reset_backend close suppressed: %s", exc)
        _BACKEND_SINGLETONS.clear()


# ---------------------------------------------------------------------------
# UID resolution
# ---------------------------------------------------------------------------
#
# Tools accept fully-qualified node uids ("code:file:foo.py",
# "code:function:foo.py::bar", "doc:file:README.md", "folder:src/utils").
# Agents (and humans) often pass a raw repo path because that is the most
# natural mental model. _resolve_uid bridges the gap by transparently
# retrying a small set of well-known prefixes when the literal lookup
# misses, and _fail_uid_not_found returns the candidates tried plus a
# scheme cheat-sheet so failures are self-explanatory.

_UID_PATH_PREFIXES: tuple[str, ...] = (
    "code:file:",
    "doc:file:",
    "folder:",
)

_UID_FORMAT_HINT = (
    "uids follow the scheme code:file:<path> | "
    "code:function:<path>::<name> | code:class:<path>::<name> | "
    "code:module:<dotted> | doc:file:<path> | "
    "doc:heading:<path>#<slug>:<level> | folder:<path>. "
    "Use cos_graph_query to discover candidates."
)

# F7b: prefix-noise tokens that pollute uid-based personalisation. Drop
# from the haystack so ranking queries like "function" / "src" don't
# spuriously match every node. Lowercase comparison.
_UID_PREFIX_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "code", "doc", "folder", "cos", "external", "unresolved",
        "file", "function", "class", "method", "module", "heading",
        "mcp_tool", "route", "frontmatter", "interface", "variable",
        "src",
    }
)

# F4 / F2 / shared: edge types that represent *behavioural* dependency
# (a real call / construction / dispatch / import) — promoting a
# behavioural edge to `will_break` in impact analysis, or counting it
# as a usage site in rename planning. Structural edges (`contains`,
# `tested_by`) are deliberately excluded. Single SSOT shared by
# `cos_graph_impact`, `cos_graph_rename_plan`, and any future tier
# logic — keeps the three call sites in lockstep.
_BEHAVIOURAL_EDGE_TYPES: frozenset[str] = frozenset(
    {
        "calls",
        "imports",
        "constructs",
        "accesses_field",
        "has_param_type",
        "has_return_type",
        "returns_type",
        "inherits_from",
        "implements",
        "dispatches",
        "awaits",
        "is_decorated_by",
        "handles_route",
        "handles_event",
        "handles_tool",
        "references_doc",
    }
)


# G6/G7: stdlib + common third-party module names that pollute the
# centrality / ranking output when not excluded. Project-internal
# modules (`core.thinking_os.server` etc.) stay in scope.
_NOISE_MODULE_NAMES: frozenset[str] = frozenset(
    {
        "__future__", "abc", "argparse", "ast", "asyncio", "base64",
        "builtins", "collections", "concurrent", "contextlib", "copy",
        "csv", "dataclasses", "datetime", "decimal", "difflib", "enum",
        "functools", "glob", "hashlib", "heapq", "http", "importlib",
        "inspect", "io", "ipaddress", "itertools", "json", "logging",
        "math", "multiprocessing", "operator", "os", "pathlib", "pickle",
        "platform", "pprint", "queue", "random", "re", "secrets",
        "select", "shutil", "signal", "socket", "sqlite3", "stat",
        "string", "struct", "subprocess", "sys", "tempfile", "textwrap",
        "threading", "time", "tomllib", "traceback", "types", "typing",
        "unittest", "urllib", "uuid", "warnings", "weakref", "xml",
        "yaml", "zipfile",
        # very common third-party that pollutes hubs
        "pytest", "click", "anyio", "httpx", "pydantic", "fastapi",
        "requests", "numpy",
    }
)


# G8/G9/G39: kind-weighting for resolve / context / query — real
# symbols rank above imports + external stubs at the same FTS5 score.
_KIND_RESOLVE_WEIGHT: dict[str, int] = {
    "class": 1, "code:class": 1,
    "function": 2, "code:function": 2,
    "method": 3, "code:method": 3,
    "interface": 4, "code:interface": 4,
    "variable": 5, "code:variable": 5,
    "mcp_tool": 6, "hook": 6, "tool": 6, "route": 6,
    "module": 10, "code:module": 10,
    "file": 11, "code:file": 11, "doc:file": 12, "doc:heading": 13,
    "import_": 20, "code:import": 20,
    "identifier": 30,  # `code:external:unresolved:*` lives here
}


def _KIND_RESOLVE_RANK(node: GraphNode) -> tuple[int, int]:
    """Lower tuple == better. Tie-break by uid length (shorter is canonical)."""
    weight = _KIND_RESOLVE_WEIGHT.get(node.kind or "", 25)
    if (node.uid or "").startswith("code:external:"):
        weight += 5
    return (weight, len(node.uid or ""))


# W7.8 / R4-12: in-repo modules that act as stub-hubs because every
# Python file imports from them. Treat them like ``code:external:*``
# in path-BFS to prevent meaningless bridges.
_PATH_STUB_HUB_MODULES: frozenset[str] = frozenset(
    {
        "__future__",
        "__init__",
        "typing",
        "typing_extensions",
        "annotations",
        "builtins",
    }
)


def _is_stub_hub_uid(uid: str) -> bool:
    """True when uid is a stub-hub (external stub or in-repo module hub)."""
    if uid.startswith("code:external:"):
        return True
    if uid.startswith("code:module:"):
        module = uid.split(":", 2)[-1]
        last = module.rsplit(".", 1)[-1]
        return last in _PATH_STUB_HUB_MODULES or module in _PATH_STUB_HUB_MODULES
    return False


# R4-02: per-node-kind default edge types for cos_graph_references.
# A class is referenced by `constructs` (instantiation) — different
# vocabulary than how a function is referenced (`calls`). Pick the
# edge-types relevant to the node's kind so the default answer for
# "who references X?" is meaningful for every kind, not just functions.
_REFERENCE_KINDS_BY_NODE_KIND: dict[str, tuple[str, ...]] = {
    "class": (
        "constructs",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "is_decorated_by",
        "imports",
        "references_doc",
    ),
    "interface": (
        "implements",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "imports",
    ),
    "function": (
        "calls",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "method": (
        "calls",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "variable": (
        "accesses_field",
        "has_param_type",
        "references_doc",
    ),
    "module": (
        "imports",
        "calls",
        "references_doc",
    ),
    "file": (
        "imports",
        "links_to",
        "references_doc",
        "contains",
    ),
    "doc_file": (
        "links_to",
        "cites_heading",
        "references_doc",
        "read_next",
    ),
    "doc_heading": (
        "links_to",
        "cites_heading",
        "references_doc",
    ),
    "folder": (
        "contains",
        "links_to",
        "references_doc",
    ),
    "mcp_tool": (
        "calls",
        "dispatches",
        "references_doc",
    ),
    "hook": (
        "handles_tool",
        "handles_event",
        "declares",
        "references_doc",
    ),
}


def _default_reference_kinds_for(node_kind: str | None) -> tuple[str, ...]:
    """Pick default inbound edge-types based on node kind (R4-02)."""
    if not node_kind:
        return ("calls", "accesses_field", "imports", "references_doc")
    return _REFERENCE_KINDS_BY_NODE_KIND.get(
        node_kind,
        ("calls", "accesses_field", "imports", "references_doc"),
    )


def _normalize_kinds(kinds: Any) -> tuple[str, ...]:
    # G3: FastMCP wire can deliver Sequence[str] as stringified JSON.
    # Accept list/CSV/JSON-array-string/single-stringified-list.
    if kinds is None:
        return ()
    if isinstance(kinds, str):
        s = kinds.strip()
        if not s:
            return ()
        if s.startswith("[") and s.endswith("]"):
            try:
                import json as _json

                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    return tuple(str(x).strip() for x in parsed if str(x).strip())
            except Exception:
                pass
        return tuple(p.strip() for p in s.split(",") if p.strip())
    if isinstance(kinds, (list, tuple)):
        if len(kinds) == 1 and isinstance(kinds[0], str) and kinds[0].lstrip().startswith("["):
            return _normalize_kinds(kinds[0])
        return tuple(str(k).strip() for k in kinds if str(k).strip())
    return ()


def _looks_prefixed(raw: str) -> bool:
    """True when input already carries an explicit uid scheme."""
    head = raw.split("/", 1)[0]
    return ":" in head


def _resolve_uid(
    backend: GraphBackend, raw_uid: str
) -> tuple[GraphNode | None, list[str], str]:
    """Look up a node uid, with path-prefix fallback for raw paths.

    Returns ``(node, tried, source)`` where ``tried`` is the ordered list
    of candidates attempted and ``source`` is one of ``direct`` |
    ``path_prefix`` | ``fuzzy_fts5`` | ``not_found``.

    R4-01: bare identifiers used to silently fall through to FTS5 fuzzy
    and return a plausible-but-wrong symbol. After fix, FTS5 fallback
    fires only for identifier-shaped inputs (``_looks_like_label``) and
    callers surface ``meta.resolved_from="fuzzy_fts5"`` so the agent can
    tell the answer came from a fuzzy match instead of an explicit lookup.
    """
    direct = backend.get_node(raw_uid)
    if direct is not None:
        return direct, [raw_uid], "direct"

    if _looks_prefixed(raw_uid):
        return None, [raw_uid], "not_found"

    tried: list[str] = [raw_uid]
    for prefix in _UID_PATH_PREFIXES:
        candidate = f"{prefix}{raw_uid}"
        tried.append(candidate)
        node = backend.get_node(candidate)
        if node is not None:
            return node, tried, "path_prefix"

    if _looks_like_label(raw_uid):
        fts_node = _fts5_label_lookup(backend, raw_uid)
        if fts_node is not None:
            tried.append(f"fts5:{raw_uid}")
            return fts_node, tried, "fuzzy_fts5"
    return None, tried, "not_found"


def _looks_like_label(raw: str) -> bool:
    if len(raw) < 3:
        return False
    if not any(c.isalpha() for c in raw):
        return False
    return all(c.isalnum() or c in "_." for c in raw)


def _fts5_label_lookup(backend: GraphBackend, raw_label: str) -> GraphNode | None:
    """Pick the top-ranked FTS5 hit whose label matches `raw_label`."""
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is None:
        return None
    row_to_node = getattr(backend, "_row_to_node", None)
    if row_to_node is None:
        return None
    fts_q = _fts5_safe_query(raw_label)
    if not fts_q:
        return None
    try:
        rows = sqlite_conn.execute(
            """
            SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                   n.end_line, n.signature, n.lang, n.doc_blob,
                   n.ast_hash, n.content_hash, n.metadata_json
            FROM graph_nodes_fts
            JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
            WHERE graph_nodes_fts MATCH ?
            ORDER BY rank
            LIMIT 20
            """,
            (fts_q,),
        ).fetchall()
    except Exception as exc:
        logger.debug("fts5 resolve fallback suppressed: %s", exc)
        return None
    # Prefer an exact label match if FTS5 surfaces one; otherwise take
    # the top-ranked hit so a near-match still resolves.
    # G9: rank candidates by kind weight (real symbol > doc heading >
    # import > external) — F11 fallback used to return whatever FTS5
    # ranked first, including doc:heading when caller wanted code:function.
    nodes = [row_to_node(r) for r in rows]
    nodes = [n for n in nodes if n is not None]
    for n in nodes:
        if (n.label or "") == raw_label and not (n.uid or "").startswith("code:external:"):
            return n
    if nodes:
        return sorted(nodes, key=_KIND_RESOLVE_RANK)[0]
    return None


def _fail_uid_not_found(
    raw_uid: str,
    tried: list[str],
    *,
    label: str = "uid",
) -> dict[str, Any]:
    """Helpful 'not_found' envelope including the candidates tried."""
    if len(tried) > 1:
        suggestions = ", ".join(repr(c) for c in tried[1:])
        msg = f"no node with {label} {raw_uid!r} (also tried {suggestions}). {_UID_FORMAT_HINT}"
    else:
        msg = f"no node with {label} {raw_uid!r}. {_UID_FORMAT_HINT}"
    return _fail("not_found", msg)


# ---------------------------------------------------------------------------
# Shared retrieval helpers
# ---------------------------------------------------------------------------


@dataclass
class NodeSummary:
    uid: str
    kind: str
    label: str
    file_path: str | None
    start_line: int | None
    # Optional centrality / hub score, populated by exporters that
    # have a degree map handy (graph_export, graph_query). None when
    # the caller did not pre-compute degrees.
    degree: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "uid": self.uid,
            "kind": self.kind,
            "label": self.label,
            "file_path": self.file_path,
            "start_line": self.start_line,
        }
        if self.degree is not None:
            out["degree"] = self.degree
        return out

    @classmethod
    def from_node(cls, node: GraphNode, *, degree: int | None = None) -> NodeSummary:
        return cls(
            uid=node.uid,
            kind=node.kind,
            label=node.label,
            file_path=node.file_path,
            start_line=node.start_line,
            degree=degree,
        )


def _degree_map_for(backend: GraphBackend, uids: Sequence[str]) -> dict[str, int]:
    """Server-side degree count for a node set.

    Cheaper than the client recomputing on every render: one query per
    export instead of N. Falls back to {} when the backend is not
    SQLite-backed (Kuzu can extend later) so consumers can degrade
    gracefully.
    """
    if not uids:
        return {}
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is None:
        return {}
    placeholders = ",".join("?" * len(uids))
    try:
        rows = sqlite_conn.execute(
            f"""
            SELECT n.uid, COUNT(*)
            FROM graph_edges_v12 e
            JOIN graph_nodes n ON n.id = e.source_id OR n.id = e.target_id
            WHERE n.uid IN ({placeholders})
            GROUP BY n.uid
            """,
            tuple(uids),
        ).fetchall()
    except Exception as exc:
        logger.debug("degree query suppressed: %s", exc)
        return {}
    return {row[0]: int(row[1]) for row in rows}


def _edge_to_dict(edge: GraphEdge, *, include_evidence: bool = False) -> dict[str, Any]:
    # TASK-122: surface provenance derived from extractor — additive,
    # never replaces the existing extractor field.  Hub UI consumers
    # (ImpactPanel, ContextPanel) can colour or filter by this label
    # without parsing extractor IDs.
    from ..types import provenance_for

    out: dict[str, Any] = {
        "source_uid": edge.source_uid,
        "target_uid": edge.target_uid,
        "edge_type": edge.edge_type,
        "confidence": edge.confidence,
        "extractor": edge.extractor,
        "provenance": provenance_for(edge.extractor),
        "source_span": edge.source_span,
    }
    if include_evidence:
        out["evidence"] = [
            {"signal_name": s.signal_name, "weight": s.weight, "note": s.note}
            for s in edge.evidence
        ]
    return out


def _file_contained_symbols(
    backend: GraphBackend, file_uid: str, *, limit: int = 500
) -> list[str]:
    # W6.3 (F6/B15/N1): when caller hands us a `code:file:*` uid the
    # interesting blast radius lives on the SYMBOLS the file contains
    # (class/function/method), not on the file node itself. Return the
    # contains-children that have behavioural inbound surface area —
    # so impact + detect_changes can roll the file-level answer up from
    # the contained symbols.
    try:
        edges = backend.list_edges(
            source_uid=file_uid, edge_types=("contains",), limit=limit
        )
    except (BackendUnavailable, sqlite3.Error):
        # Read-fallback only — caller already has a valid root node;
        # missing contained-symbol expansion degrades to file-only walk.
        # Narrowed from bare-except so KeyboardInterrupt/SystemExit propagate.
        return []
    out: list[str] = []
    for e in edges:
        tgt = e.target_uid
        # Only symbol uids carry behavioural inbound edges.
        if tgt.startswith(("code:class:", "code:function:", "code:method:")):
            out.append(tgt)
    return out


def _walk_bfs(
    backend: GraphBackend,
    *,
    root_uid: str,
    direction: str,
    max_hops: int,
    confidence_min: float,
    edge_types: Sequence[str] | None,
    visit_limit: int = 500,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """BFS traversal — shared by context / impact / trace.

    direction: "out" (source→target), "in" (target→source), or "both".

    B2: edges are only recorded the first time they lead to an unseen
    neighbour — this stops duplicate edges piling up when a neighbour is
    reached through multiple predecessors. Edges already traversed from
    either direction via the (source, target, edge_type, extractor)
    identity are suppressed.
    B6: uses ``get_nodes_bulk`` on the frontier instead of one get_node
    per neighbour, collapsing the N+1 pattern.
    """
    edges_out: list[GraphEdge] = []
    seen_edge_ids: set[tuple[str, str, str, str]] = set()
    root_nodes = _bulk_nodes(backend, [root_uid])
    root_node = root_nodes.get(root_uid)
    if root_node is None:
        return [], []

    seen_nodes: dict[str, GraphNode] = {root_uid: root_node}
    visited_uids: set[str] = {root_uid}
    queue: deque[tuple[str, int]] = deque([(root_uid, 0)])

    while queue and len(seen_nodes) < visit_limit:
        uid, depth = queue.popleft()
        if depth >= max_hops:
            continue
        neighbours: list[GraphEdge] = []
        if direction in ("out", "both"):
            neighbours.extend(
                backend.list_edges(
                    source_uid=uid,
                    edge_types=edge_types,
                    confidence_min=confidence_min,
                    limit=visit_limit,
                )
            )
        if direction in ("in", "both"):
            neighbours.extend(
                backend.list_edges(
                    target_uid=uid,
                    edge_types=edge_types,
                    confidence_min=confidence_min,
                    limit=visit_limit,
                )
            )

        frontier_uids: list[str] = []
        frontier_edges: list[GraphEdge] = []
        for edge in neighbours:
            identity = (
                edge.source_uid,
                edge.target_uid,
                edge.edge_type,
                edge.extractor,
            )
            if identity in seen_edge_ids:
                continue
            seen_edge_ids.add(identity)
            next_uid = edge.target_uid if edge.source_uid == uid else edge.source_uid
            # B2: only append when the neighbour is new — stops the edge
            # duplication that happened when the same node was reached
            # via multiple edges from different frontiers.
            if next_uid in visited_uids:
                continue
            frontier_edges.append(edge)
            frontier_uids.append(next_uid)

        if frontier_uids:
            fetched = _bulk_nodes(backend, frontier_uids)
            for edge, next_uid in zip(frontier_edges, frontier_uids):
                node = fetched.get(next_uid)
                if node is None:
                    continue
                edges_out.append(edge)
                if next_uid in visited_uids:
                    continue
                visited_uids.add(next_uid)
                seen_nodes[next_uid] = node
                queue.append((next_uid, depth + 1))
    return list(seen_nodes.values()), edges_out


def _contains_ancestors(
    backend: GraphBackend,
    *,
    leaf_uid: str,
    max_hops: int = 16,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Walk the CONTAINS spine from ``leaf_uid`` up to the repo root."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen: set[str] = {leaf_uid}
    current = leaf_uid
    for _ in range(max_hops):
        inbound = backend.list_edges(
            target_uid=current,
            edge_types=("contains",),
            limit=50,
        )
        if not inbound:
            break
        # Pick the first stable parent — spine edges are 1:N on outbound
        # but 1:1 on inbound once de-duplicated; iterate until we find
        # one we haven't visited.
        parent_edge = None
        for edge in inbound:
            if edge.source_uid not in seen:
                parent_edge = edge
                break
        if parent_edge is None:
            break
        parent_uid = parent_edge.source_uid
        seen.add(parent_uid)
        parent_node = backend.get_node(parent_uid)
        if parent_node is None:
            break
        nodes.append(parent_node)
        edges.append(parent_edge)
        current = parent_uid
        if parent_uid == "folder:.":
            break
    # Return root → leaf order so the caller can render breadcrumbs
    # left-to-right.
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def _bulk_nodes(backend: GraphBackend, uids: Sequence[str]) -> dict[str, GraphNode]:
    """B6: prefer backend.get_nodes_bulk; fall back to per-uid for legacy."""
    bulk = getattr(backend, "get_nodes_bulk", None)
    if callable(bulk):
        return bulk(list(uids))
    out: dict[str, GraphNode] = {}
    for uid in uids:
        node = backend.get_node(uid)
        if node is not None:
            out[uid] = node
    return out


# ---------------------------------------------------------------------------
# The 11 tools
# ---------------------------------------------------------------------------


def cos_graph_query(
    q: str,
    *,
    kinds: Sequence[str] | None = None,
    limit: int = 10,
    max_hops: int = 2,
    confidence_min: float = 0.3,
    include_spine: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hybrid search over node labels + docstrings.

    DEPENDS:      GraphBackend.
    """
    # G3: normalize kinds (handles wire-stringified list trap)
    parsed_kinds = _normalize_kinds(kinds)
    if (not q or not q.strip()) and not parsed_kinds:
        return _fail(
            "validation", "query must be a non-empty string (or provide kinds for kind-only browse)"
        )
    # G32: single-char queries produce 100-row token bombs (LIKE '%x%'
    # matches every identifier containing 'x'). Require ≥2 chars unless
    # kind-only browse.
    if q and q.strip() and len(q.strip()) < 2 and not parsed_kinds:
        return _fail("validation", "query must be ≥2 chars (or pass kinds for kind-only browse)")
    # W7.1 / R4-08/R4-26: limit + confidence_min validation
    err = _validate_positive_int(limit, "limit")
    if err:
        return err
    err = _validate_confidence(confidence_min, "confidence_min")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    kinds_filter = parsed_kinds if parsed_kinds else None
    nodes = _lexical_search(be, q=q, kinds=kinds_filter, limit=limit, max_hops=max_hops)

    # Fallback — when lexical hybrid returns nothing AND the query
    # *looks* like a path or uid, try _resolve_uid so agents who pass
    # "adapters/claude/sdk_dispatcher.py" or "ClaudeSDKDispatcher.dispatch"
    # get a hit instead of an empty list. Cheap (one DB lookup) and
    # additive — successful searches are untouched. Kind filter still
    # applies: if the resolved node's kind isn't allowed, skip the
    # fallback so behaviour matches the no-fallback path.
    if not nodes and q and q.strip():
        candidate = q.strip()
        looks_pathlike = (
            "/" in candidate
            or "::" in candidate
            or candidate.endswith((".py", ".ts", ".tsx", ".sh", ".md", ".yaml"))
            or _looks_prefixed(candidate)
        )
        if looks_pathlike:
            resolved, _tried, _src = _resolve_uid(be, candidate)
            if resolved is not None and (kinds_filter is None or resolved.kind in kinds_filter):
                nodes = [resolved]

    results = [
        {
            **NodeSummary.from_node(n).to_dict(),
            "confidence": 1.0,
        }
        for n in nodes
    ]
    # S3: when include_spine is set, attach a ``spine`` list per result
    # — the CONTAINS-ancestor chain from repo-root down to the result.
    if include_spine:
        for result_dict, node in zip(results, nodes):
            ancestors, _ = _contains_ancestors(be, leaf_uid=node.uid)
            result_dict["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
    # B22: cap meta.query to 500 chars with ellipsis suffix so the
    # envelope stays bounded regardless of how long the query string is.
    _MAX_QUERY_META = 500
    query_meta = q if len(q) <= _MAX_QUERY_META else q[:_MAX_QUERY_META] + "..."

    # TASK-075: process grouping.  Group hit uids by Louvain community
    # so the Search tab can render `LoginFlow` / `RegistrationFlow`
    # buckets.  Communities are computed lazily per backend with a
    # cheap edge-count signature; queries with no clustering signal
    # see an empty `processes` list and the UI falls back to flat.
    processes: list[dict[str, Any]] = []
    try:
        from .. import communities as comm_mod

        all_communities, _membership = comm_mod.compute_communities(be)
        relevant_uids = {n.uid for n in nodes}
        processes = comm_mod.communities_to_processes(all_communities, relevant_uids=relevant_uids)
    except Exception as exc:
        logger.debug("community grouping suppressed: %s", exc)
        processes = []

    total = len(results)
    # G25: omit `processes` from payload when empty so the envelope
    # shape doesn't carry a constant noise key. Keep `process_count`
    # in meta so callers can detect community-grouping availability.
    payload: dict[str, Any] = {
        "results": results[:limit],
        "total_count": total,
    }
    if processes:
        payload["processes"] = processes
    return _ok(
        payload,
        meta={
            "query": query_meta,
            "backend": be.backend_id,
            "include_spine": include_spine,
            "process_count": len(processes),
            "limit": limit,
            "result_truncated": total > limit,
        },
    )


def cos_graph_context(
    uid_or_name: str,
    *,
    direction: str = "both",
    depth: int = 1,
    include_content: bool = False,
    include_evidence: bool = False,
    include_spine: bool = False,
    visit_limit: int = 500,
    backend: str | None = None,
) -> dict[str, Any]:
    """Neighbourhood around a node.

    Coverage: when the BFS hits ``visit_limit`` before exhausting the
    reachable frontier the result is incomplete — ``data.meta.walk_truncated``
    surfaces that signal so callers can re-run with a higher cap or a
    smaller ``depth``. (Distinct from the envelope-level ``meta.truncated``
    which signals *token-budget* trimming applied by the response layer.)
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    root, tried_uids, resolved_from = _resolve_uid(be, uid_or_name)
    if root is None:
        root = _fuzzy_resolve(be, uid_or_name)
        if root is not None:
            resolved_from = "fuzzy_label"
    if root is None:
        return _fail_uid_not_found(uid_or_name, tried_uids, label="uid_or_name")

    # TASK-035: two response shapes by depth.
    #   depth=1 → full (UI path: ~2KB typical, ContextPanel renders nodes)
    #   depth>=2 → SUMMARY (agent path: counts + top-5 sample per edge_type,
    #              drops full `neighbours`). Graph must be CHEAPER than file
    #              reads — at depth=2 on a 150-caller hub, dumping 108 full
    #              NodeSummary entries (~50KB) defeats the entire point of
    #              the graph layer. Agent gets actionable summary; if it
    #              needs more, it calls cos_graph_references(target_uid).
    _depth = max(1, int(depth))
    visit_limit = max(1, min(int(visit_limit), 50_000))
    if _depth >= 2 and visit_limit > 50:
        visit_limit = 50
    nodes, edges = _walk_bfs(
        be,
        root_uid=root.uid,
        direction=direction,
        max_hops=_depth,
        confidence_min=0.0,
        edge_types=None,
        visit_limit=visit_limit,
    )
    truncated = len(nodes) >= visit_limit
    nodes_by_uid = {n.uid: n for n in nodes}
    nodes_by_uid[root.uid] = root

    def _node_dict(node: GraphNode) -> dict[str, Any]:
        d = NodeSummary.from_node(node).to_dict()
        if include_content:
            snippet = _read_node_content(node)
            if snippet is not None:
                d["content"] = snippet["content"]
                d["truncated"] = snippet["truncated"]
        return d

    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        other_uid = e.target_uid if e.source_uid == root.uid else e.source_uid
        other = nodes_by_uid.get(other_uid)
        if other is None:
            continue
        if _depth == 1:
            full_entry: dict[str, Any] = {
                "uid": other.uid,
                "kind": other.kind,
                "label": other.label,
                "edge_type": e.edge_type,
                "confidence": e.confidence,
                "extractor": e.extractor,
            }
            if include_evidence and e.evidence:
                full_entry["evidence"] = [
                    {"signal_name": s.signal_name, "weight": s.weight, "note": s.note}
                    for s in e.evidence
                ]
            grouped.setdefault(e.edge_type, []).append(full_entry)
        else:
            # Summary mode — uid+label only. Caller drills via references.
            summary_entry = {
                "uid": other.uid,
                "label": other.label,
                "edge_type": e.edge_type,
            }
            grouped.setdefault(e.edge_type, []).append(summary_entry)

    extra_meta: dict[str, Any] = {}
    if _depth == 1:
        payload: dict[str, Any] = {
            "node": _node_dict(root),
            "neighbours": [_node_dict(n) for n in nodes if n.uid != root.uid],
            "edges_by_type": grouped,
            "edge_count": len(edges),
        }
    else:
        # Summary shape — counts + top-5 sample per edge_type. No raw
        # `neighbours` (redundant + huge on high fan-in). `edge_counts`
        # tells the agent the shape; `top_edges_by_type` shows
        # representative items to drill into via cos_graph_references.
        edge_counts = {k: len(v) for k, v in grouped.items()}
        top_edges = {k: v[:5] for k, v in grouped.items()}
        payload = {
            "node": _node_dict(root),
            "edge_counts": edge_counts,
            "top_edges_by_type": top_edges,
            "edge_count": len(edges),
            "summary_mode": True,
        }
        # drill_hint lives in meta (diagnostic), not payload — saves
        # 92 bytes per call × every depth>=2 invocation at scale.
        extra_meta["drill_hint"] = (
            "depth>=2 returns summary only. For full edge list call "
            "cos_graph_references(uid, kinds=[edge_type], limit=...)."
        )
    if include_spine:
        # S3: surface the CONTAINS-ancestor chain (repo-root → … → leaf)
        # so the SPA can render breadcrumbs alongside the context view.
        ancestors, spine_edges = _contains_ancestors(be, leaf_uid=root.uid)
        payload["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
        payload["spine_edges"] = [_edge_to_dict(e) for e in spine_edges]
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "depth": depth,
            "direction": direction,
            "include_spine": include_spine,
            "visit_limit": visit_limit,
            "walk_truncated": truncated,
            "resolved_from": resolved_from,
            **extra_meta,
        },
    )


def cos_graph_impact(
    uid: str,
    *,
    direction: str = "downstream",
    depth: int = 3,
    confidence_min: float = 0.3,
    visit_limit: int = 500,
    backend: str | None = None,
) -> dict[str, Any]:
    """Blast-radius: which nodes depend on (or are depended on by) `uid`.

    Direction semantics (B12):
      "downstream" — nodes that DEPEND ON `uid` (inbound edges from
                     their perspective, i.e. direction="in" in BFS).
                     These are the nodes that WILL BREAK if `uid`
                     changes. Example: callers of a function.

      "upstream"   — nodes that `uid` DEPENDS ON (outbound edges from
                     `uid`'s perspective, i.e. direction="out" in BFS).
                     These are the nodes `uid` CALLS / IMPORTS. Changes
                     to upstream nodes may require `uid` to adapt.
                     Example: libraries or helpers that `uid` imports.

      "both"       — walks in both directions simultaneously.

    DEPRECATION NOTE: the string "downstream" / "upstream" naming
      matches the semantic intent (downstream = consumers, upstream =
      dependencies). The legacy mapping to BFS direction is preserved
      exactly. Do NOT pass raw BFS direction strings ("in"/"out") to
      this parameter — they are unsupported and will default to "in".
    """
    # W7.1 / R4-19/R4-20: confidence in [0,1] + depth>=1.
    err = _validate_confidence(confidence_min, "confidence_min")
    if err:
        return err
    err = _validate_positive_int(depth, "depth")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    walk_direction = {"downstream": "in", "upstream": "out", "both": "both"}.get(direction, "in")
    visit_limit = max(1, min(int(visit_limit), 50_000))

    # W6.3 (N1): file uids have ~no behavioural inbound edges of their
    # own — the blast radius lives on contained symbols. Walk each child
    # and merge the dedup'd union so callers asking about a file get a
    # meaningful answer instead of will_break=[].
    walk_roots = [root.uid]
    expanded_from_file = False
    if root.kind == "file":
        children = _file_contained_symbols(be, root.uid, limit=visit_limit)
        if children:
            # Children carry the behavioural surface area; the file uid
            # itself has only contains-edges (already walked as parents
            # of each child) and would consume visit_limit budget for
            # zero new signal. Drop it.
            walk_roots = children
            expanded_from_file = True

    seen_node_uids: set[str] = set()
    edges: list[GraphEdge] = []
    nodes: list[GraphNode] = []
    seen_edge_keys: set[tuple] = set()
    for sub_root in walk_roots:
        if len(seen_node_uids) >= visit_limit:
            break
        sub_nodes, sub_edges = _walk_bfs(
            be,
            root_uid=sub_root,
            direction=walk_direction,
            max_hops=max(1, int(depth)),
            confidence_min=confidence_min,
            edge_types=None,
            visit_limit=max(1, visit_limit - len(seen_node_uids)),
        )
        for n in sub_nodes:
            if n.uid in seen_node_uids:
                continue
            seen_node_uids.add(n.uid)
            nodes.append(n)
        for e in sub_edges:
            key = (e.source_uid, e.target_uid, e.edge_type)
            if key in seen_edge_keys:
                continue
            seen_edge_keys.add(key)
            edges.append(e)
    truncated = len(seen_node_uids) >= visit_limit
    tiers: dict[str, list[dict[str, Any]]] = {
        "will_break": [],
        "should_review": [],
        "context": [],
    }
    # F4 / Audit #5: tier classification is edge-type-aware, not pure
    # confidence. `contains` (file→class) has confidence=1.0 but is
    # structural — it never "breaks" when the target changes. Only
    # behavioural edges (calls / imports / constructs / type-usage /
    # dispatch / handler-binding) belong in `will_break`. Single SSOT
    # in `_BEHAVIOURAL_EDGE_TYPES` (module-level) so rename_plan +
    # impact stay in lockstep.
    for edge in edges:
        if edge.edge_type in _BEHAVIOURAL_EDGE_TYPES:
            if edge.confidence >= 0.7:
                bucket = "will_break"
            elif edge.confidence >= 0.4:
                bucket = "should_review"
            else:
                bucket = "context"
        else:
            # Structural / metadata edge (contains, tested_by, …) —
            # never a break risk; surface as context so the consumer
            # still sees the relationship.
            bucket = "context"
        tiers[bucket].append(_edge_to_dict(edge))

    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "direction": direction,
            "tiers": tiers,
            "impacted_count": max(0, len(nodes) - 1),
        },
        meta={
            "backend": be.backend_id,
            "depth": depth,
            "confidence_min": confidence_min,
            "visit_limit": visit_limit,
            "walk_truncated": truncated,
            "semantic_scope": "transitive_depth_" + str(depth),
            "expanded_from_file": expanded_from_file,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_detect_changes(
    *,
    scope: str = "working",
    files: Sequence[str] | None = None,
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Pre-commit self-review: map changed files to affected graph nodes."""
    # G3: normalize files (FastMCP wire trap)
    parsed_files = _normalize_kinds(files)
    if not parsed_files:
        return _ok(
            {
                "scope": scope,
                "files": [],
                "symbols": [],
                "downstream_tasks": [],
                "risk_level": "none",
            },
            meta={"reason": "no files provided"},
        )
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    affected_symbols: list[dict[str, Any]] = []
    downstream_tasks: set[str] = set()
    risk = "low"
    _DC_VISIT_LIMIT = 500
    walk_truncated = False

    for file_path in parsed_files:
        file_uid = f"code:file:{file_path}"
        node = be.get_node(file_uid)
        if node is None:
            continue
        nodes_1, edges = _walk_bfs(
            be,
            root_uid=file_uid,
            direction="both",
            max_hops=1,
            confidence_min=0.0,
            edge_types=None,
            visit_limit=_DC_VISIT_LIMIT,
        )
        if len(nodes_1) >= _DC_VISIT_LIMIT:
            walk_truncated = True
        for edge in edges:
            affected_symbols.append(
                {
                    "file": file_path,
                    "source": edge.source_uid,
                    "target": edge.target_uid,
                    "edge_type": edge.edge_type,
                }
            )
            # B15: collect task uids from both the 1-hop walk and, below,
            # the deep walk (depth 3, confidence >= 0.6).
            for uid_candidate in (edge.source_uid, edge.target_uid):
                if uid_candidate.startswith("task:file:"):
                    downstream_tasks.add(uid_candidate)
        if analyze_downstream:
            # W6.3 (F6/B15): walk from each contained SYMBOL (class/function/
            # method) instead of the file uid alone. File-level walk only
            # surfaces folder-contains parents — useless for risk. Roll the
            # behavioural inbound counts UP to file-level risk.
            walk_seeds = _file_contained_symbols(be, file_uid, limit=_DC_VISIT_LIMIT)
            if not walk_seeds:
                walk_seeds = [file_uid]
            seen_uids: set[str] = set()
            deep_edges: list[GraphEdge] = []
            seen_edges: set[tuple] = set()
            for seed in walk_seeds:
                if len(seen_uids) >= _DC_VISIT_LIMIT:
                    walk_truncated = True
                    break
                nodes_deep, sub_edges = _walk_bfs(
                    be,
                    root_uid=seed,
                    direction="in",
                    max_hops=3,
                    confidence_min=0.6,
                    edge_types=None,
                    visit_limit=max(1, _DC_VISIT_LIMIT - len(seen_uids)),
                )
                for n in nodes_deep:
                    seen_uids.add(n.uid)
                for e in sub_edges:
                    k = (e.source_uid, e.target_uid, e.edge_type)
                    if k in seen_edges:
                        continue
                    seen_edges.add(k)
                    deep_edges.append(e)
            if len(seen_uids) >= _DC_VISIT_LIMIT:
                walk_truncated = True
            # B15: also collect task uids from the deep (depth-3) walk.
            for deep_edge in deep_edges:
                for uid_candidate in (deep_edge.source_uid, deep_edge.target_uid):
                    if uid_candidate.startswith("task:file:"):
                        downstream_tasks.add(uid_candidate)
            # G19: risk reflects BLAST RADIUS (callers / behavioural
            # consumers), not contains-children inside the file. A new
            # file with 30 functions but zero callers is "low", not "high".
            behavioural = [
                e for e in deep_edges
                if e.edge_type in _BEHAVIOURAL_EDGE_TYPES
            ]
            if len(behavioural) > 20:
                risk = "high"
            elif len(behavioural) > 5 and risk != "high":
                risk = "medium"

    return _ok(
        {
            "scope": scope,
            "files": list(files),
            "symbols": affected_symbols,
            "downstream_tasks": sorted(downstream_tasks),
            "risk_level": risk,
        },
        meta={
            "backend": be.backend_id,
            "analyze_downstream": analyze_downstream,
            "visit_limit": _DC_VISIT_LIMIT,
            "walk_truncated": walk_truncated,
        },
    )


def cos_graph_trace(
    entry_uid: str,
    *,
    terminals: Sequence[str] = ("return", "exception"),
    max_steps: int = 50,
    include_external: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Forward execution walk from an entry point.

    F9 / Audit #7: `include_external=False` (default) keeps unresolved
    builtins / stdlib stubs (`code:external:*`) out of `steps`. They
    are collected in `external_targets` instead so the walk surface
    stays project-internal but the call-site relationship is still
    visible.
    """
    # W7.1 / R4-07: max_steps=0 returned empty steps + walk_truncated=true
    # (never walked). Reject as validation error.
    err = _validate_positive_int(max_steps, "max_steps")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_entry_uids, resolved_from = _resolve_uid(be, entry_uid)
    start_source = "explicit"
    if root is None:
        # TASK-081: fall back to the highest-scoring entry point whose
        # label / file matches the supplied identifier.  Lets agents
        # call cos_graph_trace("login") without first running a
        # separate query to resolve the uid. The entry_points module
        # is part of an in-flight TASK; tolerate its absence so the
        # tool still returns a useful not_found instead of crashing.
        try:
            from .. import entry_points as ep_mod  # type: ignore[attr-defined]

            ep = ep_mod.best_start_for_query(be, entry_uid)
            if ep is not None:
                root = be.get_node(ep.uid)
                start_source = "entry-point-heuristic"
        except ImportError as exc:
            logger.debug("entry_points fallback unavailable: %s", exc)
    if root is None:
        return _fail_uid_not_found(entry_uid, tried_entry_uids, label="entry_uid")

    steps: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    external_targets: list[str] = []
    seen: set[str] = set()
    stack: list[str] = [root.uid]
    while stack and len(steps) < max_steps:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        if not include_external and uid.startswith("code:external:"):
            external_targets.append(uid)
            continue
        node = be.get_node(uid)
        if node is None:
            continue
        steps.append(NodeSummary.from_node(node).to_dict())
        # B3: follow a wider set of outgoing control-flow edges so traces
        # cover API routes, MCP tool dispatch, event handlers, and async
        # awaits — not just direct calls/constructs.
        edges = be.list_edges(
            source_uid=uid,
            edge_types=(
                "calls",
                "constructs",
                "handles_route",
                "handles_tool",
                "handles_event",
                "dispatches",
                "awaits",
            ),
            limit=20,
        )
        if len(edges) > 1:
            # G24: strip externals from fan_out — they already live in
            # `external_targets`, so duplicating them in branches inflates
            # the envelope without new information.
            fan_out_uids = [e.target_uid for e in edges]
            if not include_external:
                fan_out_uids = [u for u in fan_out_uids if not u.startswith("code:external:")]
            branches.append(
                {
                    "from": uid,
                    "fan_out": fan_out_uids,
                }
            )
        for edge in edges:
            if edge.target_uid not in seen:
                stack.append(edge.target_uid)
    # Walk stopped either because the stack drained (complete) or
    # because the step cap fired (incomplete — caller should re-run
    # with a higher max_steps or split the trace at a branch).
    walk_truncated = len(steps) >= max_steps and bool(stack)
    return _ok(
        {
            "entry": NodeSummary.from_node(root).to_dict(),
            "steps": steps,
            "branches": branches,
            "external_targets": external_targets,
            "terminals": list(terminals),
            "start_source": start_source,
        },
        meta={
            "backend": be.backend_id,
            "step_count": len(steps),
            "external_count": len(external_targets),
            "start_source": start_source,
            "max_steps": max_steps,
            "walk_truncated": walk_truncated,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_similar(
    uid: str,
    *,
    top_k: int = 5,
    confidence_min: float = 0.5,
    backend: str | None = None,
) -> dict[str, Any]:
    """Semantic similarity — I.8 baseline uses string similarity between
    labels + docstrings; I.1 BGE-M3 embeddings lift the signal later.

    B13: uses ``sample_nodes(kind, limit)`` to build a candidate pool
    from actual graph nodes of the same kind, rather than edge-endpoint
    sampling. Edge-endpoint sampling biases toward high-degree nodes;
    ``sample_nodes`` gives an unbiased draw over the node table.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    # B13: use sample_nodes for an unbiased candidate pool.
    sample_size = 200  # bounded to keep latency predictable
    sampler = getattr(be, "sample_nodes", None)
    if callable(sampler):
        raw_candidates = sampler(root.kind or None, sample_size)
    else:
        # Graceful degradation for backends that have not yet implemented
        # sample_nodes (should not happen post-S2, but kept for safety).
        raw_candidates = []
        seen_fallback: set[str] = set()
        for edge in be.list_edges(limit=sample_size):
            for side in (edge.source_uid, edge.target_uid):
                if side in seen_fallback:
                    continue
                seen_fallback.add(side)
                n = be.get_node(side)
                if n is not None:
                    raw_candidates.append(n)

    # G21: drop external/orphan/unresolved stubs from the candidate
    # pool — they otherwise dominate similarity for any noise-shaped
    # input (`unresolved:str` returned 120 noise neighbours).
    candidates = [
        n
        for n in raw_candidates
        if n.uid != uid
        and not n.uid.startswith("code:external:unresolved:")
        and n.kind != "identifier"
    ]

    # Phase I.1 — use BGE-M3 embeddings when the model is available;
    # fall back to lexical SequenceMatcher otherwise. Both signals get
    # combined linearly so partially-loaded environments still rank.
    scorer_name = "difflib-baseline"
    embed_scores: dict[str, float] = {}
    try:
        from thinking_os.embeddings import (  # type: ignore
            cosine_similarity,
            embed_text,
            is_available,
        )

        if is_available():
            ref_text = (f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}").strip()
            ref_vec = embed_text(ref_text)
            if ref_vec:
                cand_texts = [
                    f"{n.label or ''} {n.signature or ''} {n.doc_blob or ''}".strip()
                    for n in candidates
                ]
                # batch encode candidate side, then cosine in one shot
                cand_vecs: list[bytes | None] = [embed_text(t) for t in cand_texts]
                valid = [v for v in cand_vecs if v]
                if valid:
                    sims = cosine_similarity(ref_vec, valid)
                    valid_iter = iter(sims)
                    for n, vec in zip(candidates, cand_vecs):
                        if vec is not None:
                            embed_scores[n.uid] = float(next(valid_iter))
                    scorer_name = "bge-m3+difflib-blend"
    except ImportError as exc:
        logger.debug("embeddings module unavailable: %s", exc)
    except Exception as exc:
        logger.debug("embedding similarity skipped: %s", exc)

    scored = []
    reference = f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}"
    for node in candidates:
        other = f"{node.label or ''} {node.signature or ''} {node.doc_blob or ''}"
        lex = difflib.SequenceMatcher(None, reference, other).ratio()
        emb = embed_scores.get(node.uid)
        # Linear blend: 70% embedding, 30% lexical when embedding ran;
        # 100% lexical otherwise. Keeps results deterministic and lets
        # cold-start environments still answer.
        ratio = (0.7 * emb + 0.3 * lex) if emb is not None else lex
        if ratio >= confidence_min:
            scored.append((ratio, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_k_eff = max(1, top_k)
    total = len(scored)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[:top_k_eff]
    ]
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "results": results,
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "scorer": scorer_name,
            "top_k": top_k_eff,
            "result_truncated": total > top_k_eff,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_references(
    uid: str,
    *,
    kinds: Sequence[str] | str | None = None,
    limit: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """Inbound edges to `uid` — "who references this?".

    Coverage contract (so silent truncation can't bite the agent):
      - ``count`` is the rows in *this* response (≤ limit).
      - ``total_count`` is the TRUE inbound-edge count across the kinds
        filter. If ``count < total_count`` the response is incomplete —
        the agent must either widen ``limit`` or narrow ``kinds``.
      - ``meta.result_truncated`` mirrors the same condition for fast
        inspection. (Distinct from the envelope-level ``meta.truncated``
        which signals *token-budget* truncation; result_truncated signals
        the caller-budget hit.)
    """
    # G22: validate + clamp limit
    if limit is not None and limit <= 0:
        return _fail("validation", "limit must be > 0")
    _LIMIT_MAX = 10_000
    limit_clamped = False
    if limit and limit > _LIMIT_MAX:
        limit = _LIMIT_MAX
        limit_clamped = True
    # G2 + G3: normalize kinds (caller-supplied wins; per-kind default
    # below kicks in only when caller passes empty).
    parsed_kinds = _normalize_kinds(kinds)

    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    node, tried_uids, resolved_from = _resolve_uid(be, uid)
    if node is None:
        return _fail_uid_not_found(uid, tried_uids)

    # R4-02: per-kind default — class nodes are accessed via `constructs`
    # (test instantiations) which is NOT in the function-default. Pick a
    # sensible default per node.kind so callers don't get 0 callers on a
    # class that has 30+ test constructs.
    defaults_were_picked = False
    if not parsed_kinds:
        parsed_kinds = _default_reference_kinds_for(node.kind)
        defaults_were_picked = True

    canonical_uid = node.uid
    edges = be.list_edges(target_uid=canonical_uid, edge_types=parsed_kinds, limit=limit)

    # True total — separate count query so the caller knows if `edges`
    # is a complete picture or a slice. Uses the same kinds filter
    # because the backend's list_edges does the same filtering.
    total = _count_edges_for(
        be, target_uid=canonical_uid, edge_types=parsed_kinds
    )
    truncated = total > len(edges)

    return _ok(
        {
            "node": NodeSummary.from_node(node).to_dict(),
            "references": [_edge_to_dict(e) for e in edges],
            "count": len(edges),
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "kinds": list(parsed_kinds),
            "limit": limit,
            "limit_clamped": limit_clamped,
            "result_truncated": truncated,
            "resolved_from": resolved_from,
            "default_kinds_picked": defaults_were_picked,
            "node_kind": node.kind,
        },
    )


def _count_edges_for(
    backend: GraphBackend,
    *,
    target_uid: str | None = None,
    source_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
) -> int:
    """Count edges matching the filter — separate from list_edges so the
    caller can know "you got N of M". Walks SQLite directly when the
    backend exposes ``_conn`` (the production path); falls back to
    pulling a large list and counting it for stub backends (tests).
    """
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is not None:
        where = []
        params: list[Any] = []
        if source_uid is not None:
            where.append("n_src.uid = ?")
            params.append(source_uid)
        if target_uid is not None:
            where.append("n_tgt.uid = ?")
            params.append(target_uid)
        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            where.append(f"e.edge_type IN ({placeholders})")
            params.extend(edge_types)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
          SELECT COUNT(*)
          FROM graph_edges_v12 e
          JOIN graph_nodes n_src ON n_src.id = e.source_id
          JOIN graph_nodes n_tgt ON n_tgt.id = e.target_id
          {clause}
        """
        return int(sqlite_conn.execute(sql, params).fetchone()[0])
    # Stub backend path — pull a generous slice and count it.
    edges = backend.list_edges(
        source_uid=source_uid,
        target_uid=target_uid,
        edge_types=tuple(edge_types) if edge_types else None,
        limit=10_000,
    )
    return len(edges)


def cos_graph_path(
    source_uid: str,
    target_uid: str,
    *,
    max_hops: int = 5,
    allow_external_intermediates: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Shortest path between two nodes (any direction).

    B4: each hop pulls up to 1000 edges from the backend (up from 200).
    When either side's edge list hits that cap the result is flagged
    ``meta.truncated=True`` so callers know the search may have missed a
    shorter path that lives beyond the first 1000 neighbours.

    W6.4 (T1): `code:external:*` stubs are excluded from intermediate
    hops by default because `unresolved:str` has thousands of in-edges
    and produces meaningless bridges between unrelated nodes. Pass
    ``allow_external_intermediates=True`` to opt back in.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    src_node, tried_src, src_resolved_from = _resolve_uid(be, source_uid)
    if src_node is None:
        return _fail_uid_not_found(source_uid, tried_src, label="source_uid")
    tgt_node, tried_tgt, tgt_resolved_from = _resolve_uid(be, target_uid)
    if tgt_node is None:
        return _fail_uid_not_found(target_uid, tried_tgt, label="target_uid")
    source_uid = src_node.uid
    target_uid = tgt_node.uid
    # G11/G23/P5: separate the two distinct truncation concepts:
    #   * `walk_truncated` — search ran out of budget BEFORE reaching target
    #     (the previous "truncated" semantics blurred this with fanout-cap).
    #   * `frontier_saturated` — per-node fanout hit the cap (search may
    #     still have succeeded, but a wider neighbour list could yield a
    #     shorter path). Was the original `walk_truncated` semantics —
    #     renamed to stop the false-positive panic on 3-hop paths.
    # P5: hop edge cap reduced 1000 → 200 to stay sub-100ms at 1M-node.
    _PATH_HOP_LIMIT = 200
    frontier_saturated = False
    # W6.4 (T2): parents stores (prev_uid, edge, traversal_direction).
    parents: dict[str, tuple[str, GraphEdge, str] | None] = {source_uid: None}
    queue: deque[tuple[str, int]] = deque([(source_uid, 0)])
    found = source_uid == target_uid
    while queue and not found:
        uid, depth = queue.popleft()
        if uid == target_uid:
            found = True
            break
        if depth >= max_hops:
            continue
        out_edges = be.list_edges(source_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(out_edges) >= _PATH_HOP_LIMIT:
            frontier_saturated = True
        for edge in out_edges:
            nxt = edge.target_uid
            # W6.4 (T1) + W7.8 (R4-12): skip external stubs AND in-repo
            # stub-hub modules (__future__, typing, __init__, …) which
            # bridge unrelated nodes. Target uid always exempt.
            if (
                not allow_external_intermediates
                and _is_stub_hub_uid(nxt)
                and nxt != target_uid
            ):
                continue
            if nxt not in parents:
                parents[nxt] = (uid, edge, "forward")
                queue.append((nxt, depth + 1))
        in_edges = be.list_edges(target_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(in_edges) >= _PATH_HOP_LIMIT:
            frontier_saturated = True
        for edge in in_edges:
            nxt = edge.source_uid
            if (
                not allow_external_intermediates
                and _is_stub_hub_uid(nxt)
                and nxt != target_uid
            ):
                continue
            if nxt not in parents:
                parents[nxt] = (uid, edge, "reverse")
                queue.append((nxt, depth + 1))
    walk_truncated = (target_uid not in parents) and frontier_saturated
    if target_uid not in parents:
        return _ok(
            {
                "path": None,
                "edges": [],
                "walk_truncated": walk_truncated,
                "frontier_saturated": frontier_saturated,
            },
            meta={
                "backend": be.backend_id,
                "reason": "unreachable" if not frontier_saturated else "exhausted_budget",
                "walk_truncated": walk_truncated,
                "frontier_saturated": frontier_saturated,
                "max_hops": max_hops,
                "frontier_edge_limit": _PATH_HOP_LIMIT,
                "source_resolved_from": src_resolved_from,
                "target_resolved_from": tgt_resolved_from,
            },
        )
    chain: list[tuple[GraphEdge, str]] = []
    cur = target_uid
    while parents.get(cur) is not None:
        prev, edge, traversal_dir = parents[cur]  # type: ignore[misc]
        chain.append((edge, traversal_dir))
        cur = prev
    chain.reverse()
    # G29: walk the chain step-by-step so we don't emit consecutive
    # duplicate nodes. The previous "[source] + [e.target if e.source==source
    # else e.source for e]" was anchored to the original source, which broke
    # past the first hop.
    path_nodes: list[str] = [source_uid]
    prev_uid = source_uid
    edge_dicts: list[dict[str, Any]] = []
    for e, traversal_dir in chain:
        nxt_uid = e.target_uid if e.source_uid == prev_uid else e.source_uid
        path_nodes.append(nxt_uid)
        prev_uid = nxt_uid
        # W6.4 (T2): tag each edge with how the BFS traversed it so callers
        # can tell semantic-direction edges from reverse-edge bridges.
        ed = _edge_to_dict(e)
        ed["traversal_direction"] = traversal_dir
        edge_dicts.append(ed)
    return _ok(
        {
            "path": path_nodes,
            "edges": edge_dicts,
            "hops": len(chain),
            "walk_truncated": False,
            "frontier_saturated": frontier_saturated,
        },
        meta={
            "backend": be.backend_id,
            "walk_truncated": False,
            "frontier_saturated": frontier_saturated,
            "max_hops": max_hops,
            "frontier_edge_limit": _PATH_HOP_LIMIT,
            "allow_external_intermediates": allow_external_intermediates,
            "source_resolved_from": src_resolved_from,
            "target_resolved_from": tgt_resolved_from,
        },
    )


# TASK-141: edge categories that drive the new view modes.
_SEMANTIC_EDGES: tuple[str, ...] = (
    "calls",
    "imports",
    "inherits_from",
    "implements",
    "extends",
    "dispatches",
    "handles_route",
    "handles_tool",
    "handles_event",
    "constructs",
    "awaits",
    "references",
    "references_doc",
    "is_decorated_by",
)

_CONTAINS_EDGES: tuple[str, ...] = ("contains",)

# Noise nodes that pollute the graph viewer when shown.  They're real
# graph data (extracted by md_links / frontmatter parsers) but they're
# not navigation targets — they belong in the docs RAG, not the canvas.
_DEFAULT_NOISE_KINDS: frozenset[str] = frozenset(
    {
        # Pure metadata that's already shown in the docs RAG / contains tree —
        # surfacing it on the graph canvas just creates visual noise.
        "doc:frontmatter_key",
        "doc_frontmatter",
        "doc:heading",
        "doc_heading",
        # Unresolved external identifiers (typing.*, builtins, dynamic
        # method accesses) — they're stub nodes synthesised to satisfy
        # FK constraints, not navigation targets. Hidden by default; pass
        # `exclude_kinds=""` to show them when you really need to.
        "identifier",
    }
)


# Diversified blend recipe for the auto mode (TASK-141).  Pulling the
# first N edges by confidence happens to over-represent whichever edge
# type the SQL ORDER BY surfaces first (in the live graph: handles_tool
# at 200+ rows).  Allocating per-bucket quotas guarantees every kind of
# semantic relationship lands in the result.
_AUTO_BLEND_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("calls", ("calls", "constructs")),
    ("imports", ("imports", "re_exports")),
    ("inherit", ("inherits_from", "implements", "extends")),
    ("handle", ("handles_route", "handles_tool", "handles_event", "dispatches", "defines_route")),
    ("type", ("has_param_type", "returns_type", "field_of_type", "accesses_field")),
    # Doc cross-references — `links_to` alone carries 1.5K+ edges; the
    # previous blend had no bucket so auto-mode renderings of the doc
    # subgraph showed nothing but contains spine.
    ("doc_link", ("links_to", "cites_heading", "references_doc", "read_next", "references")),
    # Decorators + module-level declarations.
    ("decoration", ("is_decorated_by", "declares")),
    ("contains", ("contains",)),
)


def cos_graph_export(
    *,
    format: str = "json",
    root_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
    max_nodes: int = 500,
    max_hops: int | None = None,
    include_spine: bool = False,
    mode: str = "auto",
    exclude_kinds: Sequence[str] | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    """Export a subgraph in `json | mermaid | dot`.

    TASK-141: ``mode`` selects the view-mode blend used when no root is
    pinned.  Hub Graph tab consumes this directly:

      - ``auto`` (default): blend of semantic (~60%) + contains (~40%).
        The previous behaviour returned 100% contains because the SQL
        order-by confidence happens to put `contains` (1.0) first —
        that's the fix the hub UI hairball needed.
      - ``containment``: contains-only (folder → file → class → method).
      - ``dependencies``: semantic-only (calls / imports / handles_* /
        inherits_from / implements / dispatches / awaits / ...).
      - ``processes``: returns Louvain community nodes + their members.

    ``exclude_kinds`` filters noise nodes (frontmatter keys, doc
    headings).  Defaults to a built-in set when None — pass an empty
    list to disable.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    if format not in {"json", "mermaid", "dot"}:
        return _fail("validation", f"unknown format {format!r}")
    if mode not in {"auto", "containment", "dependencies", "processes"}:
        return _fail(
            "validation",
            f"mode must be one of auto/containment/dependencies/processes (got {mode!r})",
        )

    # G3: normalize edge_types + exclude_kinds (wire trap)
    parsed_edge_types = _normalize_kinds(edge_types) or None
    # exclude_kinds None → default noise list; [] explicit → no filter.
    if exclude_kinds is None:
        excluded = _DEFAULT_NOISE_KINDS
    else:
        parsed_exclude_kinds = _normalize_kinds(exclude_kinds)
        excluded = frozenset(parsed_exclude_kinds)
    # G35: enforce a hard global cap on max_nodes so non-root export
    # cannot blow past the budget per-component aggregation.
    max_nodes = max(1, min(int(max_nodes), 2000))

    if root_uid is not None:
        # Hub Graph tab "depth=all" sent max_nodes=10000 but the walk
        # stopped at 3 hops, so subfolder contents never appeared
        # (user-reported: "max doesn't show 100%"). Accept the
        # frontend's depth choice and clamp to a safe ceiling.
        effective_hops = 3 if max_hops is None else max(1, min(int(max_hops), 16))
        nodes, edges = _walk_bfs(
            be,
            root_uid=root_uid,
            direction="both",
            max_hops=effective_hops,
            confidence_min=0.0,
            edge_types=parsed_edge_types,
            visit_limit=max_nodes,
        )
    elif mode == "processes":
        nodes, edges = _export_processes(be, max_nodes=max_nodes)
    else:
        nodes, edges = _export_blend(
            be,
            mode=mode,
            edge_types=parsed_edge_types,
            max_nodes=max_nodes,
        )
    # G35: hard-enforce node cap after blend (per-bucket leak).
    if len(nodes) > max_nodes:
        nodes = nodes[:max_nodes]
        kept_uids = {n.uid for n in nodes}
        edges = [e for e in edges if e.source_uid in kept_uids and e.target_uid in kept_uids]

    # TASK-141: apply noise filter.  Drop nodes whose kind is in
    # ``excluded`` AND drop any edges that touch them.
    if excluded:
        nodes = [n for n in nodes if (n.kind or "") not in excluded]
        kept_uids = {n.uid for n in nodes}
        edges = [e for e in edges if e.source_uid in kept_uids and e.target_uid in kept_uids]

    # S3: when include_spine is set, extend the subgraph with the
    # CONTAINS-ancestor chain of the root (or the deepest file node
    # present when no root is specified) so the tree-view has a
    # connected Folder→...→leaf backbone.
    if include_spine:
        seed_uid = root_uid
        if seed_uid is None:
            for n in nodes:
                if (n.kind or "").startswith(("file", "code:file", "doc:file")):
                    seed_uid = n.uid
                    break
        if seed_uid:
            ancestors, spine_edges = _contains_ancestors(be, leaf_uid=seed_uid)
            existing_uids = {n.uid for n in nodes}
            for a in ancestors:
                if a.uid not in existing_uids:
                    nodes.append(a)
                    existing_uids.add(a.uid)
            edges = list(edges) + list(spine_edges)

    if format == "json":
        # Server-side degree map so consumers (3D adapter, search,
        # NodeInspector) all see the same hub score without each
        # recomputing client-side.
        degree_map = _degree_map_for(be, [n.uid for n in nodes])
        node_dicts = [
            NodeSummary.from_node(n, degree=degree_map.get(n.uid)).to_dict() for n in nodes
        ]
        edge_dicts = [_edge_to_dict(e) for e in edges]
        payload: dict[str, Any] = {
            "format": "json",
            "nodes": node_dicts,
            "edges": edge_dicts,
        }
    elif format == "mermaid":
        payload = {"format": "mermaid", "diagram": _to_mermaid(nodes, edges)}
    else:  # dot
        payload = {"format": "dot", "diagram": _to_dot(nodes, edges)}
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "include_spine": include_spine,
        },
    )


def _export_blend(
    be: GraphBackend,
    *,
    mode: str,
    edge_types: Sequence[str] | None,
    max_nodes: int,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Compose the node + edge list for ``auto`` / ``containment`` /
    ``dependencies`` modes (TASK-141).

    The SQL list_edges API orders by ``(confidence DESC, id ASC)`` so
    a flat call with edge_types=None puts every contains edge
    (confidence=1.0) ahead of every semantic edge.  This helper
    explicitly partitions the budget so semantic relationships always
    land in the result.
    """
    if edge_types is not None:
        edges = list(be.list_edges(edge_types=tuple(edge_types), limit=max_nodes))
    elif mode == "containment":
        edges = list(be.list_edges(edge_types=_CONTAINS_EDGES, limit=max_nodes))
    elif mode == "dependencies":
        # Diversified pull across all semantic buckets so the result
        # isn't dominated by a single kind (e.g. handles_tool when MCP
        # registrations are dense).  Skip the contains bucket here.
        per_bucket = max(1, max_nodes // (len(_AUTO_BLEND_BUCKETS) - 1))
        edges = []
        for _, types in _AUTO_BLEND_BUCKETS:
            if types == _CONTAINS_EDGES:
                continue
            edges.extend(be.list_edges(edge_types=types, limit=per_bucket))
        edges = edges[:max_nodes]
    else:  # mode == "auto"
        # Equal-share quota across every bucket, then trim to budget.
        # Guarantees every semantic kind shows up alongside contains.
        per_bucket = max(1, max_nodes // len(_AUTO_BLEND_BUCKETS))
        edges = []
        for _, types in _AUTO_BLEND_BUCKETS:
            edges.extend(be.list_edges(edge_types=types, limit=per_bucket))
        edges = edges[:max_nodes]

    node_uids: set[str] = set()
    for e in edges:
        node_uids.add(e.source_uid)
        node_uids.add(e.target_uid)
    nodes = [n for n in (be.get_node(u) for u in node_uids) if n is not None]

    # Spine connectivity: walk every node up the ancestor chain so the
    # SPA's tree builder sees a connected forest. Without this, budget-
    # driven exports drop intermediate folder→file edges and the
    # orphans surface as fake "extra roots" (user's screenshot bug).
    # Only kicks in when contains is genuinely in scope — `dependencies`
    # mode promises no contains edges, so we leave its result alone.
    contains_in_scope = (
        edge_types is not None and any(t == "contains" for t in edge_types)
    ) or mode in ("auto", "containment")
    if node_uids and contains_in_scope:
        existing_pairs = {(e.source_uid, e.target_uid, e.edge_type) for e in edges}
        nodes_by_uid = {n.uid: n for n in nodes}
        for uid in list(node_uids):
            ancestors, spine_edges = _contains_ancestors(be, leaf_uid=uid)
            for a in ancestors:
                if a.uid not in nodes_by_uid:
                    nodes_by_uid[a.uid] = a
                    node_uids.add(a.uid)
            for se in spine_edges:
                key = (se.source_uid, se.target_uid, se.edge_type)
                if key not in existing_pairs:
                    edges.append(se)
                    existing_pairs.add(key)
        nodes = list(nodes_by_uid.values())

    return nodes, edges


def _export_processes(
    be: GraphBackend,
    *,
    max_nodes: int,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Return the community-driven view (TASK-141 + TASK-075).

    Each Community produces:
      - one synthetic ``cos:community`` node (label = process name)
      - real member nodes (functions / methods / classes)
      - synthetic ``member_of_community`` edges from member → community

    The synthetic nodes / edges are never persisted — they live only
    in the export response so the SPA's `Processes` view has something
    to render without polluting the SQLite tables.
    """
    from .. import communities as comm_mod

    communities, _membership = comm_mod.compute_communities(be, min_size=2)
    if not communities:
        return [], []

    community_nodes: list[GraphNode] = []
    member_nodes_by_uid: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    budget = max_nodes
    for c in communities:
        if budget <= 0:
            break
        community_uid = c.community_id
        community_nodes.append(
            GraphNode(
                uid=community_uid,
                kind="community",
                label=c.name,
                file_path=None,
                metadata={
                    "summary": c.summary,
                    "priority": c.priority,
                    "member_count": c.member_count,
                    "synthetic": True,
                },
            )
        )
        budget -= 1
        for m in c.members:
            if budget <= 0:
                break
            real = be.get_node(m["uid"])
            if real is None:
                continue
            if real.uid not in member_nodes_by_uid:
                member_nodes_by_uid[real.uid] = real
                budget -= 1
            edges.append(
                GraphEdge(
                    source_uid=real.uid,
                    target_uid=community_uid,
                    edge_type="member_of_community",
                    extractor="communities@v1",
                    confidence=1.0,
                )
            )
    return community_nodes + list(member_nodes_by_uid.values()), edges


def cos_graph_rename_plan(
    uid: str,
    new_name: str,
    *,
    check_strings: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Produce a rename plan — call-sites, docs, tests, strings."""
    if not new_name or not new_name.strip():
        return _fail("validation", "new_name must be non-empty")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)
    # R4-18: reject no-op rename (new_name equals current label)
    if new_name.strip() == (root.label or ""):
        return _fail(
            "validation",
            f"new_name {new_name!r} equals current label — no-op rename",
        )
    uid = root.uid

    # Rename plans MUST be exhaustive — a missed call-site leaves
    # broken code after rename. Counter each bucket separately so the
    # caller can see if the in-line slice was incomplete. Bucket pulls
    # from the same SSOT (`_BEHAVIOURAL_EDGE_TYPES`) impact uses,
    # minus `references_doc` which is counted under doc_edge_types
    # below to avoid double-counting.
    _RENAME_BUCKET_LIMIT = 500
    call_edge_types = tuple(
        sorted(_BEHAVIOURAL_EDGE_TYPES - {"references_doc"})
    )
    doc_edge_types = ("links_to", "cites_heading", "references_doc")
    test_edge_types = ("tested_by",)
    call_sites = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=call_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    doc_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=doc_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    test_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=test_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    call_total = _count_edges_for(be, target_uid=uid, edge_types=call_edge_types)
    doc_total = _count_edges_for(be, target_uid=uid, edge_types=doc_edge_types)
    test_total = _count_edges_for(be, target_uid=uid, edge_types=test_edge_types)
    result_truncated = (
        call_total > len(call_sites)
        or doc_total > len(doc_refs)
        or test_total > len(test_refs)
    )
    risk = "high" if len(call_sites) > 20 else "medium" if call_sites else "low"

    return _ok(
        {
            "old_name": root.label,
            "new_name": new_name,
            "uid": root.uid,
            "call_sites": call_sites,
            "call_sites_total_count": call_total,
            "doc_references": doc_refs,
            "doc_references_total_count": doc_total,
            "test_references": test_refs,
            "test_references_total_count": test_total,
            "string_literals": [] if not check_strings else _grep_string_literals(root.label or ""),
            "risk": risk,
            "suggested_order": [
                "tests first",
                "implementation",
                "docs",
                "string literals last",
            ],
            "confidence": 0.9 if call_sites else 0.6,
        },
        meta={
            "backend": be.backend_id,
            "bucket_limit": _RENAME_BUCKET_LIMIT,
            "result_truncated": result_truncated,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_contracts(
    *,
    scope: str = "all",
    kinds: Sequence[str] = ("http", "mcp", "grpc", "event", "websocket"),
    backend: str | None = None,
) -> dict[str, Any]:
    """API surface — enumerate every route / tool / event handler."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    # G3: normalize kinds (wire trap)
    parsed_kinds = _normalize_kinds(kinds)
    if not parsed_kinds:
        parsed_kinds = ("http", "mcp", "grpc", "event", "websocket")

    buckets: dict[str, list[dict[str, Any]]] = {
        "http_routes": [],
        "mcp_tools": [],
        "grpc_endpoints": [],
        "event_handlers": [],
        "websocket": [],
    }
    # Per-edge-type slice — silent truncation at limit=2000 would hide
    # contracts on a large API surface. Counter each kind so the agent
    # knows if the slice was complete.
    # G5: was 2000; default invocation blew past MCP token cap (106KB).
    # 200 per-edge-type bucket keeps the typical envelope well under
    # ~10K tokens; callers needing more can paginate.
    _CONTRACT_BUCKET_LIMIT = 200
    per_kind_truncated: dict[str, bool] = {}
    for edge_type in ("handles_route", "handles_tool", "handles_event"):
        edges_slice = be.list_edges(edge_types=(edge_type,), limit=_CONTRACT_BUCKET_LIMIT)
        total = _count_edges_for(be, edge_types=(edge_type,))
        per_kind_truncated[edge_type] = total > len(edges_slice)
        for edge in edges_slice:
            node = be.get_node(edge.target_uid)
            if node is None:
                continue
            kind = (node.metadata or {}).get("kind", "http")
            if kind not in parsed_kinds:
                continue
            bucket_key = {
                "http": "http_routes",
                "mcp": "mcp_tools",
                "grpc": "grpc_endpoints",
                "event": "event_handlers",
                "websocket": "websocket",
            }.get(kind, "http_routes")
            buckets[bucket_key].append(
                {
                    **NodeSummary.from_node(node).to_dict(),
                    "method": (node.metadata or {}).get("method"),
                    "path": (node.metadata or {}).get("path"),
                    "framework": (node.metadata or {}).get("framework"),
                    "handler": (node.metadata or {}).get("handler"),
                    "source": edge.source_uid,
                    "confidence": edge.confidence,
                }
            )
    result_truncated = any(per_kind_truncated.values())
    return _ok(
        {"scope": scope, **buckets, "count": sum(len(v) for v in buckets.values())},
        meta={
            "backend": be.backend_id,
            "kinds": list(parsed_kinds),
            "bucket_limit": _CONTRACT_BUCKET_LIMIT,
            "result_truncated": result_truncated,
            "per_edge_type_truncated": per_kind_truncated,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_node_content(node: GraphNode, *, cap: int = 2000) -> dict[str, Any] | None:
    """B21: read source snippet for a node from its file_path + line range."""
    if not node.file_path:
        return None
    try:
        src = Path(node.file_path)
        if not src.is_file():
            return None
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, (node.start_line or 1) - 1)  # 1-indexed → 0-indexed
        end = node.end_line or node.start_line or len(lines)
        snippet = "\n".join(lines[start:end])
        truncated = len(snippet) > cap
        return {"content": snippet[:cap], "truncated": truncated}
    except Exception as exc:
        logger.debug("_read_node_content skipped for %s: %s", node.uid, exc)
        return None


def _fuzzy_resolve(backend: GraphBackend, needle: str) -> GraphNode | None:
    """Fallback for `cos_graph_context("UserService")` — try a label match.

    Scans edges to collect nodes, then difflib-scores by label. Bounded
    to 200 candidates so latency is predictable.
    """
    lower = needle.lower()
    seen: dict[str, GraphNode] = {}
    for edge in backend.list_edges(limit=500):
        for side in (edge.source_uid, edge.target_uid):
            if side in seen:
                continue
            node = backend.get_node(side)
            if node is None:
                continue
            if needle in (node.uid or "") or lower in (node.label or "").lower():
                return node
            seen[side] = node
    return None


def _lexical_search(
    backend: GraphBackend,
    *,
    q: str,
    kinds: Sequence[str] | None,
    limit: int,
    max_hops: int,
) -> list[GraphNode]:
    """Multi-signal lexical search with centrality tie-breaker."""
    lower = q.lower()
    sqlite_conn = getattr(backend, "_conn", None)
    candidates: list[GraphNode] = []
    if sqlite_conn is not None:
        rows: list[Any] = []
        try:
            if not lower and kinds:
                # kinds-only browse — no text filter needed
                placeholders = ",".join(["?"] * len(kinds))
                rows = sqlite_conn.execute(
                    f"SELECT kind, label, uid, file_path, start_line, end_line,"
                    f"       signature, lang, doc_blob, ast_hash, content_hash,"
                    f"       metadata_json"
                    f" FROM graph_nodes WHERE kind IN ({placeholders}) LIMIT ?",
                    tuple(list(kinds) + [int(limit) * 6]),
                ).fetchall()
            else:
                like_q = f"%{lower}%"
                kinds_clause = ""
                params: list[Any] = [like_q, like_q, like_q]
                if kinds:
                    placeholders = ",".join(["?"] * len(kinds))
                    kinds_clause = f" AND kind IN ({placeholders})"
                    params.extend(list(kinds))
                params.append(int(limit) * 6)
                rows = sqlite_conn.execute(
                    f"""
                    SELECT kind, label, uid, file_path, start_line, end_line,
                           signature, lang, doc_blob, ast_hash, content_hash,
                           metadata_json
                    FROM graph_nodes
                    WHERE (LOWER(label) LIKE ?
                           OR LOWER(COALESCE(signature, '')) LIKE ?
                           OR LOWER(COALESCE(doc_blob, '')) LIKE ?)
                    {kinds_clause}
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
        except Exception as exc:
            logger.debug("lexical sql search suppressed: %s", exc)
        row_to_node = getattr(backend, "_row_to_node", None)
        for row in rows:
            if row_to_node is not None:
                candidates.append(row_to_node(row))
            else:
                n = backend.get_node(row[2])
                if n is not None:
                    candidates.append(n)

    if not candidates:
        seen: dict[str, GraphNode] = {}
        for edge in backend.list_edges(limit=1000):
            for side in (edge.source_uid, edge.target_uid):
                if side in seen:
                    continue
                node = backend.get_node(side)
                if node is None:
                    continue
                if kinds and node.kind not in kinds:
                    continue
                haystack = " ".join(
                    filter(
                        None,
                        [node.uid, node.label, node.signature, node.doc_blob],
                    )
                ).lower()
                if lower in haystack:
                    seen[side] = node
                if len(seen) >= limit * 3:
                    break
        candidates = list(seen.values())

    degree_map = _degree_map_for(backend, [n.uid for n in candidates])
    from math import log2

    def score(n: GraphNode) -> float:
        label = (n.label or "").lower()
        sig = (n.signature or "").lower()
        doc = (n.doc_blob or "").lower()
        if label == lower:
            base = 1.0
        elif label.startswith(lower):
            base = 0.85
        elif lower in label:
            base = 0.70
        elif lower in sig:
            base = 0.45
        elif lower in doc:
            base = 0.30
        else:
            base = difflib.SequenceMatcher(None, lower, label).ratio() * 0.5
        boost = log2((degree_map.get(n.uid) or 0) + 1) * 0.05
        # G39: penalise external stubs + identifier noise so they don't
        # outrank a real symbol at the same label match.
        kind_penalty = 0.0
        if (n.uid or "").startswith("code:external:"):
            kind_penalty = 0.5
        elif n.kind == "identifier":
            kind_penalty = 0.4
        elif (n.kind or "") in ("import_", "code:import"):
            kind_penalty = 0.2
        return base + min(boost, 0.4) - kind_penalty

    return sorted(candidates, key=score, reverse=True)[:limit]


def _grep_string_literals(name: str) -> list[dict[str, Any]]:
    """Stub for the string-scan path. Real implementation lives in CLI layer."""
    return []


def _to_mermaid(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["graph LR"]
    for n in nodes:
        lines.append(f'  {_safe_id(n.uid)}["{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(f"  {_safe_id(e.source_uid)} -->|{e.edge_type}| {_safe_id(e.target_uid)}")
    return "\n".join(lines)


def _to_dot(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["digraph G {"]
    for n in nodes:
        lines.append(f'  "{_safe_id(n.uid)}" [label="{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(
            f'  "{_safe_id(e.source_uid)}" -> "{_safe_id(e.target_uid)}" [label="{e.edge_type}"]'
        )
    lines.append("}")
    return "\n".join(lines)


def _safe_id(uid: str) -> str:
    # F5 / Audit #14: previous impl `re.sub(..., "_", uid)[:60]` made
    # every method of one class collapse to identical mermaid/dot node
    # IDs (uid prefix is the same — class+method suffix got chopped).
    # Suffix an 8-char sha1 so IDs are collision-proof regardless of uid
    # length, and keep a readable 40-char prefix for diagram legibility.
    sanitised = re.sub(r"[^A-Za-z0-9_]", "_", uid)
    if len(sanitised) <= 48:
        return sanitised
    digest = hashlib.sha1(uid.encode("utf-8")).hexdigest()[:8]
    return f"{sanitised[:40]}_{digest}"


def _escape(text: str) -> str:
    return text.replace('"', "'")


def cos_graph_entrypoints(
    *,
    top: int = 20,
    kind: str | None = None,
    min_score: float = 0.05,
    diversify: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return scored entry-point candidates (TASK-081).

    F10 / Audit #13: many real entrypoints tie at the same score and
    the pre-fix `sort(-score, uid)` made the alphabetically-first file
    monopolise the top-N. `diversify=True` (default) round-robins
    across distinct file_paths within each score tier so the top
    surfaces structurally different entrypoints. Set False to recover
    the raw score-only ranking.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if kind is not None:
        err = _validate_enum(kind, ("main", "cli", "http", "cron", "test"), "kind")
        if err:
            return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    try:
        from .. import entry_points as ep_mod  # type: ignore[attr-defined]
    except ImportError as exc:
        return _fail(
            "unavailable",
            f"entry_points module not installed: {exc}",
            retryable=False,
        )

    eps = ep_mod.discover(be, min_score=float(min_score), kind_filter=kind)
    # G20: rank cli/http/mcp/cron above tests. Audit showed top-10
    # ALL tests at the 0.85 tied score, with main()/CLI never visible.
    _KIND_PRIORITY = {
        "main": 4, "cli": 4, "http": 3, "cron": 2, "test": 1,
    }
    eps = sorted(
        eps,
        key=lambda ep: (
            -_KIND_PRIORITY.get(getattr(ep, "kind", ""), 0),
            -float(getattr(ep, "score", 0.0)),
        ),
    )
    total = len(eps)
    if diversify and eps:
        # Round-robin by file_path within each score-tier so the top-N
        # spans multiple files. Pure sort would let one file's tests
        # all alphabetise to the front.
        from collections import defaultdict

        by_file: dict[str | None, list[Any]] = defaultdict(list)
        for ep in eps:
            by_file[ep.file_path].append(ep)
        # Stable interleave: pop one entry from each file bucket per
        # round until either top or all buckets are drained.
        ordered: list[Any] = []
        files_in_score_order: list[str | None] = []
        seen_files: set[str | None] = set()
        for ep in eps:
            if ep.file_path not in seen_files:
                seen_files.add(ep.file_path)
                files_in_score_order.append(ep.file_path)
        while len(ordered) < top:
            advanced = False
            for fp in files_in_score_order:
                if by_file[fp]:
                    ordered.append(by_file[fp].pop(0))
                    advanced = True
                    if len(ordered) >= top:
                        break
            if not advanced:
                break
        eps = ordered
    rows = [ep.to_dict() for ep in eps[:top]]
    return _ok(
        {"entrypoints": rows, "total_count": total},
        meta={
            "backend": be.backend_id,
            "count": len(rows),
            "scanned_kinds": list(("code:function", "code:method", "function", "method")),
            "top": top,
            "result_truncated": total > top,
        },
    )


def cos_graph_communities(
    *,
    top: int = 50,
    min_size: int = 2,
    max_members: int = 10,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return Louvain process clusters. Response payload key is `processes`.

    F8 / Audit #9: each process embeds its member nodes. On real repos
    a single process can hold 100+ members and `top=5` returned a
    236KB envelope that blew past the MCP token budget. `max_members`
    caps the inline list per process; `member_count` still reports the
    real size, and `members_truncated` flags when the slice is short.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if not isinstance(min_size, int) or min_size < 1:
        return _fail("validation", "min_size must be >= 1")
    err = _validate_positive_int(max_members, "max_members")
    if err:
        return err
    max_members, _ = _clamp_int(max_members, min_v=1, max_v=500)
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    from .. import communities as comm_mod

    all_communities, _membership = comm_mod.compute_communities(be, min_size=int(min_size))
    rows = comm_mod.communities_to_processes(all_communities, relevant_uids=None)
    capped: list[dict[str, Any]] = []
    members_truncated = False
    # P2: adaptive envelope cap. At top=50 × default max_members=10, the
    # envelope hit 47K tokens — well past the safe ~5K threshold. Project
    # rows × members and shrink max_members or top until under budget.
    _TOKEN_TARGET = 5000
    _TOKENS_PER_MEMBER = 90  # empirical average per member entry
    _TOKENS_PER_PROCESS_HEADER = 60
    projected_top = min(top, len(rows))
    effective_max_members = max_members
    projected = (
        projected_top * _TOKENS_PER_PROCESS_HEADER
        + projected_top * effective_max_members * _TOKENS_PER_MEMBER
    )
    if projected > _TOKEN_TARGET:
        # W6.6 (B10): never shrink members below 3 — a "community" of 1
        # member kills the concept. Drop tail communities instead, then
        # only as a last resort shrink members down to 3, then 1.
        _MEMBER_FLOOR = min(3, max_members)
        # Step 1: shrink members down to the floor (or requested, whichever
        # is smaller) at current projected_top.
        budget_per_process_for_members = max(
            0, (_TOKEN_TARGET - projected_top * _TOKENS_PER_PROCESS_HEADER)
        )
        if projected_top > 0:
            effective_max_members = max(
                _MEMBER_FLOOR,
                budget_per_process_for_members
                // (projected_top * _TOKENS_PER_MEMBER),
            )
        effective_max_members = min(effective_max_members, max_members)
        # Step 2: if still over budget, drop tail communities.
        while (
            projected_top > 1
            and projected_top * (
                _TOKENS_PER_PROCESS_HEADER
                + effective_max_members * _TOKENS_PER_MEMBER
            )
            > _TOKEN_TARGET
        ):
            projected_top -= 1
        # Step 3: last resort — even 1 community at floor doesn't fit.
        # Lower the floor (1 member is still better than 0 communities).
        while (
            projected_top > 0
            and projected_top * (
                _TOKENS_PER_PROCESS_HEADER
                + effective_max_members * _TOKENS_PER_MEMBER
            )
            > _TOKEN_TARGET
            and effective_max_members > 1
        ):
            effective_max_members -= 1
        members_truncated = effective_max_members < max_members
    for row in rows[:projected_top]:
        members = row.get("members") or []
        if len(members) > effective_max_members:
            members_truncated = True
            row = {**row, "members": members[:effective_max_members]}
        capped.append(row)
    payload_truncated = projected_top < min(top, len(rows))
    return _ok(
        {"processes": capped},
        meta={
            "backend": be.backend_id,
            "count": len(capped),
            "total": len(rows),
            # back-compat: keep `max_members` key (existing tests + UI)
            "max_members": effective_max_members,
            "max_members_effective": effective_max_members,
            "max_members_requested": max_members,
            "members_truncated": members_truncated,
            "envelope_truncated": payload_truncated,
            "top_effective": projected_top,
            "top_requested": top,
        },
    )


def cos_graph_centrality(
    *,
    top: int = 20,
    kind: str | None = None,
    metric: str = "degree",
    include_external: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hub detection via degree (or betweenness) centrality.

    F6 / Audit #10: `include_external` defaults to False so unresolved
    builtins (`code:external:unresolved:str/int/bool/len`) and stdlib
    stubs (`code:external:pathlib:Path`) do not crowd the top of the
    list. Set True to opt back into the raw ranking.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    err = _validate_enum(metric, ("degree", "betweenness"), "metric")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    sqlite_conn = getattr(be, "_conn", None)
    truncated = False

    if sqlite_conn is not None:
        try:
            where_parts: list[str] = []
            params: list[Any] = []
            if kind:
                where_parts.append("n.kind = ?")
                params.append(kind)
            if not include_external:
                where_parts.append("n.uid NOT LIKE 'code:external:%'")
                # G6: also drop stdlib module hubs (`code:module:__future__`,
                # `code:module:pathlib`, ...) — F6 only kicked external out.
                stdlib_placeholders = ",".join("?" * len(_NOISE_MODULE_NAMES))
                where_parts.append(f"n.uid NOT IN ({stdlib_placeholders})")
                params.extend(f"code:module:{name}" for name in _NOISE_MODULE_NAMES)
            kind_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            in_deg_rows = sqlite_conn.execute(
                f"""
                SELECT n.uid, n.kind, n.label, COUNT(e.id) AS cnt
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 e ON e.target_id = n.id
                {kind_clause}
                GROUP BY n.id
                """,
                tuple(params),
            ).fetchall()
            out_deg_rows = sqlite_conn.execute(
                f"""
                SELECT n.uid, COUNT(e.id) AS cnt
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 e ON e.source_id = n.id
                {kind_clause}
                GROUP BY n.id
                """,
                tuple(params),
            ).fetchall()
        except Exception as exc:
            logger.debug("centrality SQL suppressed: %s", exc)
            in_deg_rows = []
            out_deg_rows = []

        out_map = {row[0]: int(row[1]) for row in out_deg_rows}
        N = len(in_deg_rows)
        norm = 2 * (N - 1) if N > 1 else 1
        rows_out = []
        for uid, nkind, label, in_cnt in in_deg_rows:
            out_cnt = out_map.get(uid, 0)
            in_cnt = int(in_cnt)
            score = (in_cnt + out_cnt) / norm
            rows_out.append(
                {
                    "uid": uid,
                    "kind": nkind,
                    "label": label,
                    "in_degree": in_cnt,
                    "out_degree": out_cnt,
                    "centrality_score": round(score, 6),
                }
            )
    else:
        # Fallback: scan edges
        in_deg: dict[str, int] = {}
        out_deg: dict[str, int] = {}
        uid_meta: dict[str, tuple[str, str]] = {}  # uid -> (kind, label)
        for edge in be.list_edges(limit=10000):
            out_deg[edge.source_uid] = out_deg.get(edge.source_uid, 0) + 1
            in_deg[edge.target_uid] = in_deg.get(edge.target_uid, 0) + 1
        all_uids = set(in_deg) | set(out_deg)
        if kind:
            filtered_uids = set()
            for u in all_uids:
                node = be.get_node(u)
                if node and node.kind == kind:
                    filtered_uids.add(u)
                    uid_meta[u] = (node.kind or "", node.label or "")
            all_uids = filtered_uids
        else:
            for u in all_uids:
                node = be.get_node(u)
                if node:
                    uid_meta[u] = (node.kind or "", node.label or "")
        N = len(all_uids)
        norm = 2 * (N - 1) if N > 1 else 1
        rows_out = []
        for u in all_uids:
            ic = in_deg.get(u, 0)
            oc = out_deg.get(u, 0)
            meta_entry = uid_meta.get(u, ("", u))
            rows_out.append(
                {
                    "uid": u,
                    "kind": meta_entry[0],
                    "label": meta_entry[1],
                    "in_degree": ic,
                    "out_degree": oc,
                    "centrality_score": round((ic + oc) / norm, 6),
                }
            )

    if metric == "betweenness" and sqlite_conn is not None:
        _BETWEENNESS_CAP = 300
        try:
            all_uids_list: list[str] = [r["uid"] for r in rows_out]
            if len(all_uids_list) > _BETWEENNESS_CAP:
                # Approximate: sample the top-degree nodes only.
                rows_out.sort(key=lambda r: r["centrality_score"], reverse=True)
                all_uids_list = [r["uid"] for r in rows_out[:_BETWEENNESS_CAP]]
                truncated = True
            uid_idx = {u: i for i, u in enumerate(all_uids_list)}
            adj: dict[int, list[int]] = {i: [] for i in range(len(all_uids_list))}
            for u in all_uids_list:
                i = uid_idx[u]
                edges_out = be.list_edges(source_uid=u, limit=500)
                for e in edges_out:
                    j = uid_idx.get(e.target_uid)
                    if j is not None:
                        adj[i].append(j)
            betweenness = _betweenness_centrality(adj, len(all_uids_list))
            bt_map = {all_uids_list[i]: v for i, v in enumerate(betweenness)}
            for r in rows_out:
                r["centrality_score"] = round(bt_map.get(r["uid"], 0.0), 6)
        except Exception as exc:
            logger.debug("betweenness computation suppressed: %s", exc)

    rows_out.sort(key=lambda r: r["centrality_score"], reverse=True)
    return _ok(
        {"nodes": rows_out[:top]},
        meta={
            "backend": be.backend_id,
            "metric": metric,
            "node_count": len(rows_out),
            "result_truncated": truncated,
        },
    )


def _betweenness_centrality(adj: dict[int, list[int]], n: int) -> list[float]:
    """Brandes' algorithm — O(V·E) exact betweenness for small graphs."""
    bet = [0.0] * n
    for s in range(n):
        stack: list[int] = []
        pred: list[list[int]] = [[] for _ in range(n)]
        sigma = [0] * n
        sigma[s] = 1
        dist = [-1] * n
        dist[s] = 0
        from collections import deque as _deque

        q: _deque[int] = _deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj.get(v, []):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = [0.0] * n
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                bet[w] += delta[w]
    norm_factor = (n - 1) * (n - 2) if n > 2 else 1
    return [v / norm_factor for v in bet]


def cos_graph_ranking(
    *,
    query: str | None = None,
    top: int = 20,
    kind: str | None = None,
    damping: float = 0.85,
    iterations: int = 30,
    include_external: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """PageRank-based node ranking with optional query personalisation.

    F6 / Audit #11: `include_external=False` (default) excludes
    unresolved-stub + stdlib nodes (`code:external:*`) from the input
    set so the top of the ranking surfaces project-internal hubs
    instead of `__future__` / `pathlib` / builtins.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if not (0.0 < damping < 1.0):
        return _fail("validation", "damping must be in (0, 1)")
    # W7.1 / R4-06: iterations=0 returned uniform vector with positive
    # rank_score that looked real. Reject as validation error.
    err = _validate_positive_int(iterations, "iterations")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    _NODE_CAP = 5000
    truncated = False
    sqlite_conn = getattr(be, "_conn", None)

    if sqlite_conn is not None:
        try:
            where_parts: list[str] = []
            params_n: list[Any] = []
            if kind:
                where_parts.append("kind = ?")
                params_n.append(kind)
            if not include_external:
                where_parts.append("uid NOT LIKE 'code:external:%'")
                # G7: drop stdlib module hubs in line with G6 centrality.
                stdlib_placeholders = ",".join("?" * len(_NOISE_MODULE_NAMES))
                where_parts.append(f"uid NOT IN ({stdlib_placeholders})")
                params_n.extend(f"code:module:{name}" for name in _NOISE_MODULE_NAMES)
            kind_filter = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            params_n.append(_NODE_CAP)
            uid_rows = sqlite_conn.execute(
                f"SELECT id, uid, kind, label, file_path, start_line "
                f"FROM graph_nodes {kind_filter} LIMIT ?",
                tuple(params_n),
            ).fetchall()
            if len(uid_rows) >= _NODE_CAP:
                truncated = True
            edge_rows = sqlite_conn.execute(
                "SELECT source_id, target_id FROM graph_edges_v12 LIMIT ?",
                (_NODE_CAP * 20,),
            ).fetchall()
        except Exception as exc:
            logger.debug("ranking SQL suppressed: %s", exc)
            uid_rows = []
            edge_rows = []
        int_to_uid = {row[0]: row[1] for row in uid_rows}
        int_to_meta: dict[int, tuple[str, str, str | None, int | None]] = {
            row[0]: (row[2], row[3], row[4], row[5]) for row in uid_rows
        }
        uid_to_int: dict[str, int] = {row[1]: row[0] for row in uid_rows}
        valid_ids = set(int_to_uid)
        out_links: dict[int, list[int]] = {i: [] for i in valid_ids}
        for src, tgt in edge_rows:
            if src in valid_ids and tgt in valid_ids:
                out_links[src].append(tgt)
        N = len(valid_ids)
        node_ids = list(valid_ids)
    else:
        # Edge-scan fallback
        uid_set: set[str] = set()
        edge_pairs: list[tuple[str, str]] = []
        for edge in be.list_edges(limit=_NODE_CAP * 10):
            uid_set.add(edge.source_uid)
            uid_set.add(edge.target_uid)
            edge_pairs.append((edge.source_uid, edge.target_uid))
        if len(uid_set) > _NODE_CAP:
            truncated = True
        node_ids_str = list(uid_set)[:_NODE_CAP]
        uid_to_int = {u: i for i, u in enumerate(node_ids_str)}
        int_to_uid = {i: u for i, u in enumerate(node_ids_str)}
        int_to_meta = {}
        valid_ids_int = set(range(len(node_ids_str)))
        out_links_str: dict[int, list[int]] = {i: [] for i in valid_ids_int}
        for s, t in edge_pairs:
            si, ti = uid_to_int.get(s, -1), uid_to_int.get(t, -1)
            if si >= 0 and ti >= 0:
                out_links_str[si].append(ti)
        out_links = out_links_str
        N = len(node_ids_str)
        node_ids = list(valid_ids_int)
        # Kind filter post-hoc
        if kind:
            keep = set()
            for nid in node_ids:
                u = int_to_uid.get(nid, "")
                node = be.get_node(u)
                if node and node.kind == kind:
                    keep.add(nid)
                    int_to_meta[nid] = (
                        node.kind or "",
                        node.label or "",
                        node.file_path,
                        node.start_line,
                    )
            node_ids = [n for n in node_ids if n in keep]
            N = len(node_ids)

    if N == 0:
        return _ok({"nodes": []}, meta={"backend": be.backend_id, "count": 0})

    # Personalisation vector: uniform unless query given.
    # F7 / Audit #12: previous matcher required the full query as a
    # substring of the label. "graph backend" matched no label literally
    # → empty vector → uniform teleport → identical to global PageRank.
    # Token-OR match: any whitespace-split token hits → seed weight ∝
    # token-hit count. Falls back to substring-AND when query has no
    # internal whitespace so single-name queries still target precisely.
    #
    # F7b: drop uid-prefix noise tokens (`code`, `function`, `module`,
    # `cos`, …) so a query like "function" or "src" does not spuriously
    # match every node via the uid string. Personalisation seed now
    # comes from content tokens only — label + uid-suffix words.
    personalized: dict[int, float] = {}
    if query:
        lower_q = query.lower().strip()
        tokens = [t for t in lower_q.split() if len(t) >= 2]
        if not tokens:
            tokens = [lower_q] if lower_q else []
        for nid in node_ids:
            meta_entry = int_to_meta.get(nid)
            label = (meta_entry[1] if meta_entry else (int_to_uid.get(nid, ""))) or ""
            uid_str = int_to_uid.get(nid, "")
            uid_content_tokens = [
                t
                for t in re.split(r"[^A-Za-z0-9]+", uid_str.lower())
                if t and t not in _UID_PREFIX_NOISE_TOKENS and len(t) >= 2
            ]
            hay = label.lower() + " " + " ".join(uid_content_tokens)
            hits = sum(1 for t in tokens if t in hay)
            if hits:
                personalized[nid] = float(hits)
        total_p = sum(personalized.values())
        if total_p:
            personalized = {k: v / total_p for k, v in personalized.items()}

    # P1: precompute in_links ONCE — was recomputed O(N²) per iter
    # inside the rank loop (35.5s p99 → ~50ms expected at N=5000).
    in_links: dict[int, list[int]] = {}
    out_link_count: dict[int, int] = {}
    for src, tgts in out_links.items():
        out_link_count[src] = len(tgts)
        for tgt in tgts:
            in_links.setdefault(tgt, []).append(src)
    # Power iteration
    rank: dict[int, float] = dict.fromkeys(node_ids, 1.0 / N)
    dangling = {nid for nid in node_ids if not out_links.get(nid)}
    for _ in range(iterations):
        dangling_sum = sum(rank[nid] for nid in dangling) / N
        new_rank: dict[int, float] = {}
        for nid in node_ids:
            inbound = in_links.get(nid, [])
            push = sum(rank[src] / out_link_count[src] for src in inbound if out_link_count.get(src))
            if personalized:
                teleport = personalized.get(nid, 0.0)
            else:
                teleport = 1.0 / N
            new_rank[nid] = (1 - damping) * teleport + damping * (push + dangling_sum)
        rank = new_rank

    results: list[dict[str, Any]] = []
    for nid, score in sorted(rank.items(), key=lambda x: x[1], reverse=True)[:top]:
        uid = int_to_uid.get(nid, "")
        meta_entry = int_to_meta.get(nid)
        if meta_entry:
            nkind, label, fpath, sline = meta_entry
        else:
            node = be.get_node(uid)
            nkind = node.kind or "" if node else ""
            label = node.label or uid if node else uid
            fpath = node.file_path if node else None
            sline = node.start_line if node else None
        results.append(
            {
                "uid": uid,
                "kind": nkind,
                "label": label,
                "rank_score": round(score, 8),
                "file_path": fpath,
                "start_line": sline,
            }
        )

    # G13: surface why personalisation didn't engage when caller passed
    # a query — silent fallback to global rank is the audit's complaint.
    personalization_reason: str | None = None
    if query and query.strip() and not personalized:
        personalization_reason = "no_candidate_labels_matched"
    return _ok(
        {"nodes": results},
        meta={
            "backend": be.backend_id,
            "node_count": N,
            "node_cap": _NODE_CAP,  # G15: was hidden default; expose it
            "iterations": iterations,
            "damping": damping,
            "result_truncated": truncated,
            "personalized": bool(personalized),
            "personalization_reason": personalization_reason,
        },
    )


def cos_graph_doctor(
    *,
    fix: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Graph health check — orphans, dangling edges, duplicates."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    sqlite_conn = getattr(be, "_conn", None)
    issues: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    fixed_count = 0

    if sqlite_conn is not None:
        try:
            node_count = sqlite_conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            edge_count = sqlite_conn.execute("SELECT COUNT(*) FROM graph_edges_v12").fetchone()[0]
            stats["node_count"] = node_count
            stats["edge_count"] = edge_count

            # 1. Dangling source edges (source_id FK points to deleted node)
            dangling_src_rows = sqlite_conn.execute(
                """
                SELECT e.id, ns.uid, nt.uid
                FROM graph_edges_v12 e
                LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE ns.id IS NULL
                LIMIT 100
                """
            ).fetchall()
            dangling_src_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges_v12 e
                LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                WHERE ns.id IS NULL
                """
            ).fetchone()[0]
            if dangling_src_count:
                issues.append(
                    {
                        "category": "dangling_source",
                        "count": dangling_src_count,
                        "sample": [
                            {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                            for r in dangling_src_rows[:5]
                        ],
                    }
                )
                if fix:
                    ids_to_del = [r[0] for r in dangling_src_rows]
                    if ids_to_del:
                        placeholders = ",".join("?" * len(ids_to_del))
                        sqlite_conn.execute(
                            f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                            ids_to_del,
                        )
                        sqlite_conn.commit()
                        fixed_count += len(ids_to_del)

            # 2. Dangling target edges (target_id FK points to deleted node)
            dangling_tgt_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges_v12 e
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE nt.id IS NULL
                """
            ).fetchone()[0]
            if dangling_tgt_count:
                dangling_tgt_rows = sqlite_conn.execute(
                    """
                    SELECT e.id, ns.uid, nt.uid
                    FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                    WHERE nt.id IS NULL
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "dangling_target",
                        "count": dangling_tgt_count,
                        "sample": [
                            {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                            for r in dangling_tgt_rows
                        ],
                    }
                )
                if fix:
                    all_dangling_tgt = sqlite_conn.execute(
                        """
                        SELECT e.id FROM graph_edges_v12 e
                        LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                        WHERE nt.id IS NULL
                        """
                    ).fetchall()
                    ids_to_del = [r[0] for r in all_dangling_tgt]
                    if ids_to_del:
                        placeholders = ",".join("?" * len(ids_to_del))
                        sqlite_conn.execute(
                            f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                            ids_to_del,
                        )
                        sqlite_conn.commit()
                        fixed_count += len(ids_to_del)

            # 3. Duplicate edges (same source_id/target_id/edge_type/extractor)
            dup_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT source_id, target_id, edge_type, extractor,
                         COUNT(*) AS cnt
                  FROM graph_edges_v12
                  GROUP BY source_id, target_id, edge_type, extractor
                  HAVING cnt > 1
                )
                """
            ).fetchone()[0]
            if dup_count:
                dup_sample = sqlite_conn.execute(
                    """
                    SELECT ns.uid, nt.uid, e.edge_type, e.extractor,
                           COUNT(*) AS cnt
                    FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                    GROUP BY e.source_id, e.target_id, e.edge_type, e.extractor
                    HAVING cnt > 1
                    ORDER BY cnt DESC
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "duplicate_edges",
                        "count": dup_count,
                        "sample": [
                            {
                                "source_uid": r[0],
                                "target_uid": r[1],
                                "edge_type": r[2],
                                "extractor": r[3],
                                "count": r[4],
                            }
                            for r in dup_sample
                        ],
                    }
                )

            # 4. Orphans — split into expected-noise vs real-bug categories.
            # W7.6 / R4-N9: `code:external:unresolved:*` and `cos:identifier:*`
            # are stub-surface, not bugs. Count separately so `healthy=true`
            # is achievable when only stubs are unconnected.
            orphan_rows = sqlite_conn.execute(
                """
                SELECT n.uid, n.kind, n.label
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 src ON src.source_id = n.id
                LEFT JOIN graph_edges_v12 tgt ON tgt.target_id = n.id
                WHERE src.id IS NULL AND tgt.id IS NULL
                """
            ).fetchall()
            real_orphans: list[tuple[str, str, str]] = []
            stub_orphans: list[tuple[str, str, str]] = []
            for uid_, kind_, label_ in orphan_rows:
                if (uid_ or "").startswith("code:external:unresolved:") or (
                    uid_ or ""
                ).startswith("cos:identifier:"):
                    stub_orphans.append((uid_, kind_, label_))
                else:
                    real_orphans.append((uid_, kind_, label_))
            stats["orphaned_nodes"] = len(orphan_rows)
            stats["orphaned_inrepo"] = len(real_orphans)
            stats["orphaned_external_unresolved"] = len(stub_orphans)
            if real_orphans:
                issues.append(
                    {
                        "category": "orphaned_inrepo",
                        "count": len(real_orphans),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "label": r[2]}
                            for r in real_orphans[:5]
                        ],
                    }
                )
            if stub_orphans:
                # Informational only — never trips healthy=false.
                issues.append(
                    {
                        "category": "orphaned_external_unresolved",
                        "count": len(stub_orphans),
                        "severity": "info",
                        "sample": [
                            {"uid": r[0], "kind": r[1], "label": r[2]}
                            for r in stub_orphans[:5]
                        ],
                    }
                )

            # 5. Self-loop edges (source_id == target_id — extractor bugs)
            self_loop_count = sqlite_conn.execute(
                "SELECT COUNT(*) FROM graph_edges_v12 WHERE source_id = target_id"
            ).fetchone()[0]
            if self_loop_count:
                sl_sample = sqlite_conn.execute(
                    """
                    SELECT ns.uid, e.edge_type FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    WHERE e.source_id = e.target_id LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "self_loops",
                        "count": self_loop_count,
                        "sample": [{"uid": r[0], "edge_type": r[1]} for r in sl_sample],
                    }
                )

            # 6. Stale-path nodes — file_path points to a file that no
            # longer exists on disk. Accumulates when files move (e.g.
            # the `core/` → `src/core/` reorg left 3.7K ghost nodes
            # invisible to the dangling/orphan/self_loop checks because
            # ghosts had their own internal contains-children tree).
            distinct_paths = [
                r[0]
                for r in sqlite_conn.execute(
                    "SELECT DISTINCT file_path FROM graph_nodes "
                    "WHERE file_path IS NOT NULL AND file_path != ''"
                ).fetchall()
            ]
            repo_root = _repo_root_for_paths()
            # W7.6 / R4-25: split malformed paths (containing ../) from
            # genuine stale paths. Malformed paths are extractor bugs —
            # they can never resolve from repo root regardless of fs state.
            malformed_paths = [p for p in distinct_paths if "../" in p]
            real_stale_paths = [
                p
                for p in distinct_paths
                if "../" not in p and not (repo_root / p).exists()
            ]
            if malformed_paths:
                mp_count = sqlite_conn.execute(
                    f"SELECT COUNT(*) FROM graph_nodes WHERE file_path IN ({','.join('?' * len(malformed_paths))})",
                    malformed_paths,
                ).fetchone()[0]
                mp_sample = sqlite_conn.execute(
                    f"SELECT uid, kind, file_path FROM graph_nodes WHERE file_path IN ({','.join('?' * len(malformed_paths))}) LIMIT 5",
                    malformed_paths,
                ).fetchall()
                issues.append(
                    {
                        "category": "malformed_uid_path",
                        "count": mp_count,
                        "path_count": len(malformed_paths),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "file_path": r[2]} for r in mp_sample
                        ],
                    }
                )
                if fix:
                    chunk = 500
                    for i in range(0, len(malformed_paths), chunk):
                        batch = malformed_paths[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE file_path IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()
            stale_paths = real_stale_paths
            if stale_paths:
                stale_node_count = sqlite_conn.execute(
                    f"SELECT COUNT(*) FROM graph_nodes WHERE file_path IN ({','.join('?' * len(stale_paths))})",
                    stale_paths,
                ).fetchone()[0]
                sp_sample = sqlite_conn.execute(
                    f"SELECT uid, kind, file_path FROM graph_nodes WHERE file_path IN ({','.join('?' * len(stale_paths))}) LIMIT 5",
                    stale_paths,
                ).fetchall()
                issues.append(
                    {
                        "category": "stale_paths",
                        "count": stale_node_count,
                        "path_count": len(stale_paths),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "file_path": r[2]} for r in sp_sample
                        ],
                    }
                )
                if fix:
                    chunk = 500
                    for i in range(0, len(stale_paths), chunk):
                        batch = stale_paths[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE file_path IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()

            stats["issue_count"] = len(issues)
            if fix:
                stats["fixed_edge_count"] = fixed_count

        except Exception as exc:
            logger.debug("doctor SQL suppressed: %s", exc)
            return _ok(
                {"healthy": None, "issues": [], "stats": {}, "error": str(exc)},
                meta={"backend": be.backend_id},
            )
    else:
        # Non-SQLite backend: basic edge-endpoint check only
        seen_uids: set[str] = set()
        edge_list = be.list_edges(limit=5000)
        for edge in edge_list:
            seen_uids.add(edge.source_uid)
            seen_uids.add(edge.target_uid)
        missing = 0
        for u in list(seen_uids)[:500]:
            if be.get_node(u) is None:
                missing += 1
        if missing:
            issues.append({"category": "dangling_endpoints", "count": missing, "sample": []})
        stats["edge_count"] = len(edge_list)
        stats["issue_count"] = len(issues)

    # W7.6 / R4-N9: informational categories (orphaned_external_unresolved)
    # do NOT trip healthy=false. Real issues = anything else.
    _INFORMATIONAL_CATEGORIES = {"orphaned_external_unresolved"}
    real_issues = [
        i for i in issues if i.get("category") not in _INFORMATIONAL_CATEGORIES
    ]
    healthy = len(real_issues) == 0
    return _ok(
        {"healthy": healthy, "issues": issues, "stats": stats},
        meta={
            "backend": be.backend_id,
            "fix_applied": fix and fixed_count > 0,
            "fixed_count": fixed_count,
            # W7.6 / R4-13: list what fix=true actually deletes today.
            # orphaned_external_unresolved is informational (extractor
            # stub surfacing — not a fixable bug).
            "fixable_categories": [
                "stale_paths",
                "malformed_uid_path",
                "dangling_source",
                "dangling_target",
            ],
            "informational_categories": list(_INFORMATIONAL_CATEGORIES),
        },
    )


def cos_graph_resolve(
    q: str,
    *,
    kinds: Sequence[str] | None = None,
    top: int = 10,
    backend: str | None = None,
) -> dict[str, Any]:
    """Resolve a natural-language label, path, or partial uid to canonical uids.

    Tries three strategies in order, stopping at the first that yields hits:

    1. Direct uid lookup (when `q` already carries `code:`/`doc:`/`folder:`).
    2. Path-shaped fallback (paths, `::`-separated qualnames) → ``_resolve_uid``.
    3. FTS5 full-text search over label + signature + doc_blob — handles
       multi-word natural-language queries like "the dispatcher function"
       far better than the LIKE pattern used by ``cos_graph_query``.
    """
    # W7.1 / R4-09: parity with cos_graph_query — both require q>=2 chars.
    err = _validate_min_chars(q, "q", min_chars=2)
    if err:
        return err
    err = _validate_positive_int(top, "top")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    candidate = q.strip()
    # G3: normalize kinds (wire trap)
    parsed_kinds = _normalize_kinds(kinds)
    kinds_set = set(parsed_kinds) if parsed_kinds else None
    candidates: list[GraphNode] = []
    strategy = ""

    # Strategy 1 + 2: direct uid / path-shape resolve.
    looks_pathlike = (
        "/" in candidate
        or "::" in candidate
        or candidate.endswith((".py", ".ts", ".tsx", ".sh", ".md", ".yaml"))
        or _looks_prefixed(candidate)
    )
    if looks_pathlike:
        node, _tried, _src = _resolve_uid(be, candidate)
        if node is not None and (kinds_set is None or node.kind in kinds_set):
            candidates.append(node)
            strategy = "path_resolve"

    # Strategy 3: FTS5 — only when path-resolve missed.
    if not candidates:
        sqlite_conn = getattr(be, "_conn", None)
        if sqlite_conn is not None:
            try:
                fts_q = _fts5_safe_query(candidate)
                if fts_q:
                    rows = sqlite_conn.execute(
                        """
                        SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                               n.end_line, n.signature, n.lang, n.doc_blob,
                               n.ast_hash, n.content_hash, n.metadata_json
                        FROM graph_nodes_fts
                        JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
                        WHERE graph_nodes_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_q, int(top) * 6),
                    ).fetchall()
                    row_to_node = getattr(be, "_row_to_node", None)
                    pool: list[GraphNode] = []
                    for row in rows:
                        node = row_to_node(row) if row_to_node else None
                        if node is None:
                            continue
                        if kinds_set is not None and node.kind not in kinds_set:
                            continue
                        pool.append(node)
                    # G8: weight by kind preference — real symbols beat
                    # imports + external stubs at the same FTS5 rank.
                    candidates.extend(sorted(pool, key=_KIND_RESOLVE_RANK)[: int(top)])
                    if candidates and not strategy:
                        strategy = "fts5"
            except Exception as exc:
                logger.debug("fts5 resolve suppressed: %s", exc)

    # Strategy 4 (fallback): plain lexical search — last resort.
    if not candidates:
        candidates = _lexical_search(
            be,
            q=candidate,
            kinds=parsed_kinds if parsed_kinds else None,
            limit=int(top),
            max_hops=1,
        )
        if candidates:
            strategy = "lexical_like"

    results = [
        {
            **NodeSummary.from_node(n).to_dict(),
            "confidence": 1.0 if strategy == "path_resolve" else 0.7,
        }
        for n in candidates[:top]
    ]
    return _ok(
        {"results": results, "strategy": strategy or "miss"},
        meta={"backend": be.backend_id, "query": candidate[:200]},
    )


def _fts5_safe_query(raw: str) -> str:
    """Sanitise a free-text query for FTS5.

    FTS5 reserves `"`, `*`, `(`, `)`, `:`. We strip them rather than
    quote-escape because most agent queries are noun phrases — splitting
    into tokens with implicit AND is the highest-recall behaviour.
    Returns empty string on degenerate input so the caller skips FTS.
    """
    cleaned = []
    for ch in raw:
        if ch.isalnum() or ch in "._-":
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    tokens = [t for t in "".join(cleaned).split() if len(t) >= 2]
    if not tokens:
        return ""
    # Quote each token to handle digits + dotted names; join with space
    # so FTS5 applies an implicit AND.
    return " ".join(f'"{t}"' for t in tokens[:8])


__all__ = [
    "cos_graph_centrality",
    "cos_graph_communities",
    "cos_graph_context",
    "cos_graph_contracts",
    "cos_graph_detect_changes",
    "cos_graph_doctor",
    "cos_graph_entrypoints",
    "cos_graph_export",
    "cos_graph_impact",
    "cos_graph_path",
    "cos_graph_query",
    "cos_graph_ranking",
    "cos_graph_references",
    "cos_graph_rename_plan",
    "cos_graph_resolve",
    "cos_graph_similar",
    "cos_graph_trace",
    "reset_backend",
]
