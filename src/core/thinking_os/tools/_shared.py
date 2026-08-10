"""
Coding OS — Shared MCP tool envelope helpers.

Canonical response contract: docs/engineering/mcp-error-envelope.md.

Every `cos_*` tool registered in `server.py` MUST route its return value
through `ok()` / `fail()` so consuming agents can distinguish success from
failure, categorize errors, and decide whether to retry.

Uniform `meta` block:
    Every success payload carries `data.meta` with at minimum:
      - layer             ("memory"|"docs"|"tasks"|"metrics"|"routing"|
                           "graph"|"health"|"learning")
      - tokens_estimated  (script-aware token estimate of the serialized response)
      - truncated         (bool — set True when token budget forced a cut)

    Callers supply `meta={"layer": ..., "source": ..., "query": ...}` via
    the `ok(data, meta=...)` kwarg. `tokens_estimated` and `truncated` are
    computed by this helper — callers must not set them manually.

Token-budget enforcement:
    Serialized responses above TOKEN_BUDGET_CHARS are trimmed. Strategy:
    shrink `data.results` from the tail until the payload fits. Meta
    records both the original and kept sizes so the agent knows it asked
    for too much and can page with a smaller limit.

This module owns `ok()` and the `safe_tool` decorator. The concerns they
compose live beside them, each changing for its own reason:

    _envelope_size      token estimate + the two budgets (leaf)
    _envelope_trim      the trim ladder for oversized list payloads
    _envelope_subgraph  the connectivity-preserving graph-export trim
    _envelope_errors    fail() + the validate_* helpers that produce it
    _envelope_gating    disabled-module tool gating

They are re-exported below because callers and tests import them from here.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from functools import wraps
from typing import Any

# Dual import identity (flat `tools._shared` vs package
# `thinking_os.tools._shared` / `core.thinking_os.tools._shared`) — try the
# package form, fall back to the bare one.
try:  # package import
    from ._envelope_errors import (
        _RETRYABLE_BY_DEFAULT,
        ErrorCategory,
        clamp_int,
        fail,
        validate_confidence,
        validate_enum,
        validate_min_chars,
        validate_non_empty_str,
        validate_positive_int,
    )
    from ._envelope_gating import (
        _MODULE_GATE_CACHE,
        _disabled_modules,
        _gated_module,
        _tool_module_map,
        apply_module_tool_gating,
    )
    from ._envelope_size import (
        GRAPH_SUBGRAPH_BUDGET_CHARS,
        TOKEN_BUDGET_CHARS,
        _budget_size,
        _estimate_tokens,
        _probe_size,
    )
    from ._envelope_subgraph import _trim_coherent_subgraph
    from ._envelope_trim import (
        _SCALAR_TRIM_FLOOR_CHARS,
        _TRIMMABLE_LIST_KEYS,
        _TRIMMABLE_NESTED_BUCKETS,
        _TRIMMABLE_NESTED_MEMBERS,
        _apply_token_budget,
        _trim_edges_by_type,
        _trim_huge_string_fields,
        _trim_list_key,
        _trim_lists_balanced,
        _trim_nested_buckets,
        _trim_nested_member_lists,
    )
except ImportError:  # flat import
    from _envelope_errors import (  # type: ignore[no-redef,import-not-found]
        _RETRYABLE_BY_DEFAULT,
        ErrorCategory,
        clamp_int,
        fail,
        validate_confidence,
        validate_enum,
        validate_min_chars,
        validate_non_empty_str,
        validate_positive_int,
    )
    from _envelope_gating import (  # type: ignore[no-redef,import-not-found]
        _MODULE_GATE_CACHE,
        _disabled_modules,
        _gated_module,
        _tool_module_map,
        apply_module_tool_gating,
    )
    from _envelope_size import (  # type: ignore[no-redef,import-not-found]
        GRAPH_SUBGRAPH_BUDGET_CHARS,
        TOKEN_BUDGET_CHARS,
        _budget_size,
        _estimate_tokens,
        _probe_size,
    )
    from _envelope_subgraph import (  # type: ignore[no-redef,import-not-found]
        _trim_coherent_subgraph,
    )
    from _envelope_trim import (  # type: ignore[no-redef,import-not-found]
        _SCALAR_TRIM_FLOOR_CHARS,
        _TRIMMABLE_LIST_KEYS,
        _TRIMMABLE_NESTED_BUCKETS,
        _TRIMMABLE_NESTED_MEMBERS,
        _apply_token_budget,
        _trim_edges_by_type,
        _trim_huge_string_fields,
        _trim_list_key,
        _trim_lists_balanced,
        _trim_nested_buckets,
        _trim_nested_member_lists,
    )

logger = logging.getLogger("coding_os.tools._shared")

# Layer names — enumerated so tests can pin the contract and agents can
# filter (Three-Layer Retrieval in CLAUDE.md).
VALID_LAYERS: frozenset[str] = frozenset(
    {
        "memory",
        "docs",
        "tasks",
        "metrics",
        "routing",
        "graph",
        "health",
        "learning",
    }
)


# ---------------------------------------------------------------------------
# Success envelope
# ---------------------------------------------------------------------------


def ok(data: Any, *, meta: dict[str, Any] | None = None, apply_budget: bool = True) -> str:
    """Wrap a successful tool result in the canonical envelope."""
    if not isinstance(data, dict):
        return json.dumps({"ok": True, "data": data}, indent=2, default=str)

    # Merge caller-supplied meta on top of any meta already in data.
    # Diagnostic keys (tokens_estimated, truncated, truncated_results_*) are
    # strictly computed here — caller-supplied values are stripped so agents
    # cannot spoof "this response wasn't trimmed" in logs/audit.
    existing_meta = dict(data.get("meta") or {})
    if meta:
        existing_meta.update(meta)
    # Strip diagnostic keys the trimmer owns — caller meta can't spoof
    # them. `tokens_estimated` + `truncated` always; every `truncated_*`
    # key (added by _trim_list_key + _trim_edges_by_type) reserved too.
    for _diag in ("tokens_estimated", "truncated"):
        existing_meta.pop(_diag, None)
    for _k in [k for k in existing_meta if k.startswith("truncated_")]:
        existing_meta.pop(_k, None)

    # Strip `meta` from the data dict so we can re-attach with diagnostics
    body = {k: v for k, v in data.items() if k != "meta"}

    # First serialization to estimate tokens (meta is the in-progress dict
    # referenced below; JSON reflects current state each dump).
    serialized = json.dumps(
        {"ok": True, "data": {**body, "meta": existing_meta}},
        indent=2,
        default=str,
    )
    existing_meta["tokens_estimated"] = _estimate_tokens(serialized)
    existing_meta["truncated"] = False

    # Graph-export-shaped responses ({nodes:[...], edges:[...]}) describe a
    # whole subgraph. Two-tier budget:
    #   1. Under GRAPH_SUBGRAPH_BUDGET_CHARS (≈500 KB): pass through
    #      untouched — UI Hub needs full tree to render CONTAINS spine.
    #   2. Over the larger ceiling: coherent-subgraph trim (top-K nodes
    #      by degree + edges between kept nodes). Never zero out edges
    #      and never return an incoherent slice.
    # Agent consumers can use max_nodes/max_hops to stay under the agent
    # context window; the envelope is the safety net, not the primary cap.
    _is_graph_subgraph = (
        isinstance(body.get("nodes"), list)
        and isinstance(body.get("edges"), list)
        and bool(body.get("nodes"))
        and bool(body.get("edges"))
    )
    # Enforce token budget. `truncated` only flips when the body was
    # actually shrunk — a no-op (shape not matched) leaves the flag
    # False so agents trust the signal. Web/browser callers pass
    # apply_budget=False: a browser is not token-limited, so the 32KB
    # agent-context cap (and its envelope_unshrinkable fall-through when a
    # payload's shape isn't in the trim ladder) must not apply to it — that
    # cap is an agent-context concept, not a wire limit. Mirrors the
    # apply_budget param cos_task_board already exposes (the board's browser
    # path threads it straight through here).
    if not apply_budget:
        pass
    elif _is_graph_subgraph:
        if len(serialized) > GRAPH_SUBGRAPH_BUDGET_CHARS:
            body, existing_meta, did_trim = _trim_coherent_subgraph(
                body, existing_meta, budget_chars=GRAPH_SUBGRAPH_BUDGET_CHARS
            )
            if did_trim:
                existing_meta["truncated"] = True
                serialized = json.dumps(
                    {"ok": True, "data": {**body, "meta": existing_meta}},
                    indent=2,
                    default=str,
                )
                existing_meta["tokens_estimated"] = _estimate_tokens(serialized)
    elif _budget_size(serialized) > TOKEN_BUDGET_CHARS:
        body, existing_meta, did_trim = _apply_token_budget(body, existing_meta)
        if did_trim:
            existing_meta["truncated"] = True
            # Audit fix: a list-dropping token trim makes the
            # answer incomplete, so the coverage flag must agree. Tools
            # that publish `result_truncated` (contracts/references/...)
            # had it stay False while items were silently dropped, so an
            # agent reading only result_truncated assumed completeness.
            if "result_truncated" in existing_meta:
                existing_meta["result_truncated"] = True
            serialized = json.dumps(
                {"ok": True, "data": {**body, "meta": existing_meta}},
                indent=2,
                default=str,
            )
            existing_meta["tokens_estimated"] = _estimate_tokens(serialized)

    payload = {"ok": True, "data": {**body, "meta": existing_meta}}
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# safe_tool — the decorator every cos_* wears, and its failure forensics
# ---------------------------------------------------------------------------


def _sqlite_db_identity(args: tuple[Any, ...]) -> str:
    # Multi-process forensics (mcp-error-envelope.md § Internal-error
    # forensics): every server process appends to the same .mcp.log, so a
    # sqlite failure must name the DB file its connection was attached to.
    conn = args[0] if args and isinstance(args[0], sqlite3.Connection) else None
    if conn is None:
        return ""
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
        return " db=" + ";".join(str(row[2]) for row in rows)
    except sqlite3.Error:
        return " db=<database_list unavailable>"


def _log_tool_failure(tool_name: str, exc: Exception, args: tuple[Any, ...]) -> None:
    db_identity = _sqlite_db_identity(args) if isinstance(exc, sqlite3.Error) else ""
    logger.exception(
        "tool %s raised %s [pid=%d thread=%s]%s",
        tool_name,
        type(exc).__name__,
        os.getpid(),
        threading.current_thread().name,
        db_identity,
    )


def safe_tool(
    fn: Callable[..., str] | None = None,
    *,
    name: str | None = None,
) -> Callable[..., str] | Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator: convert unhandled exceptions inside a tool to `fail()`.

    Mapping is conservative — specific Python exception types map to the
    closest envelope category; anything unrecognized becomes `internal`.
    Place this INSIDE `@mcp.tool(...)` so MCP still sees a string return:

        @mcp.tool(name="cos_example", ...)
        @safe_tool
        def cos_example(...) -> str:
            ...

    Pass `name=` when the Python function name differs from the registered MCP
    tool name (e.g. `thinking_os_search` registered as `cos_search`) so the
    subsystems module gate keys on the name `subsystems.yaml` lists, not the
    internal function name. Without it the gate silently never fires for that
    tool.
    """

    def decorate(target: Callable[..., str]) -> Callable[..., str]:
        gate_name = name or target.__name__

        @wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            gated_by = _gated_module(gate_name)
            if gated_by:
                return fail(
                    "module_disabled",
                    f"tool '{gate_name}' belongs to the disabled '{gated_by}' module — "
                    f"enable it with `cos module enable {gated_by}`",
                    retryable=False,
                )
            try:
                result = target(*args, **kwargs)
            except PermissionError as exc:
                _log_tool_failure(gate_name, exc, args)
                return fail("permission", str(exc) or "permission denied", retryable=False)
            except FileNotFoundError as exc:
                _log_tool_failure(gate_name, exc, args)
                return fail("not_found", str(exc) or "resource not found", retryable=False)
            except (TimeoutError, ConnectionError) as exc:
                _log_tool_failure(gate_name, exc, args)
                return fail("transient", str(exc) or type(exc).__name__, retryable=True)
            except ValueError as exc:
                _log_tool_failure(gate_name, exc, args)
                return fail("validation", str(exc) or "invalid input", retryable=False)
            except ImportError as exc:
                _log_tool_failure(gate_name, exc, args)
                return fail(
                    "unavailable", str(exc) or "optional dependency missing", retryable=True
                )
            except Exception as exc:
                _log_tool_failure(gate_name, exc, args)
                return fail("internal", f"{type(exc).__name__}: {exc}", retryable=False)

            # Name the offending tool when ok() flagged the envelope unshrinkable.
            # ok() logs the size from a context without the tool name, leaving the
            # eye with an unactionable "something is 265KB" error.
            if isinstance(result, str) and "envelope_unshrinkable" in result:
                logger.error(
                    "tool %s returned an unshrinkable envelope (%d chars > %d budget)",
                    gate_name,
                    len(result),
                    TOKEN_BUDGET_CHARS,
                )
            return result

        return wrapper

    # Bare `@safe_tool` → fn is the target. `@safe_tool(name=...)` → fn is None.
    return decorate(fn) if fn is not None else decorate


__all__ = [
    "GRAPH_SUBGRAPH_BUDGET_CHARS",
    "TOKEN_BUDGET_CHARS",
    "VALID_LAYERS",
    "_MODULE_GATE_CACHE",
    "_RETRYABLE_BY_DEFAULT",
    "_SCALAR_TRIM_FLOOR_CHARS",
    "_TRIMMABLE_LIST_KEYS",
    "_TRIMMABLE_NESTED_BUCKETS",
    "_TRIMMABLE_NESTED_MEMBERS",
    "ErrorCategory",
    "_apply_token_budget",
    "_budget_size",
    "_disabled_modules",
    "_estimate_tokens",
    "_gated_module",
    "_log_tool_failure",
    "_probe_size",
    "_sqlite_db_identity",
    "_tool_module_map",
    "_trim_coherent_subgraph",
    "_trim_edges_by_type",
    "_trim_huge_string_fields",
    "_trim_list_key",
    "_trim_lists_balanced",
    "_trim_nested_buckets",
    "_trim_nested_member_lists",
    "apply_module_tool_gating",
    "clamp_int",
    "fail",
    "ok",
    "safe_tool",
    "validate_confidence",
    "validate_enum",
    "validate_min_chars",
    "validate_non_empty_str",
    "validate_positive_int",
]
