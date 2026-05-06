"""
Coding OS — Shared MCP tool envelope helpers.

Canonical response contract: docs/engineering/mcp-error-envelope.md.

Every `cos_*` tool registered in `server.py` MUST route its return value
through `ok()` / `fail()` so consuming agents can distinguish success from
failure, categorize errors, and decide whether to retry.

Phase G.3 addition — uniform `meta` block:
    Every success payload carries `data.meta` with at minimum:
      - layer             ("memory"|"docs"|"tasks"|"metrics"|"routing"|
                           "graph"|"health"|"learning")
      - tokens_estimated  (serialized response length ÷ 4)
      - truncated         (bool — set True when token budget forced a cut)

    Callers supply `meta={"layer": ..., "source": ..., "query": ...}` via
    the `ok(data, meta=...)` kwarg. `tokens_estimated` and `truncated` are
    computed by this helper — callers must not set them manually.

Phase G.5 addition — token-budget enforcement:
    Serialized responses above TOKEN_BUDGET_CHARS are trimmed. Strategy:
    shrink `data.results` from the tail until the payload fits. Meta
    records both the original and kept sizes so the agent knows it asked
    for too much and can page with a smaller limit.
"""

from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any, Callable, Literal

logger = logging.getLogger("coding_os.tools._shared")

ErrorCategory = Literal[
    "transient",
    "validation",
    "permission",
    "not_found",
    "unavailable",
    "internal",
]

_RETRYABLE_BY_DEFAULT: frozenset[str] = frozenset({"transient", "unavailable"})

# 32 KB ≈ 8 000 tokens. Sized to fit 4× the largest typical cos_doc_search
# response (≈2k tokens) so normal traffic never hits the budget, while
# catastrophic payloads (e.g. 1000-row metric queries) get trimmed.
TOKEN_BUDGET_CHARS = 32_000

# Layer names — enumerated so tests can pin the contract and agents can
# filter (Three-Layer Retrieval in CLAUDE.md).
VALID_LAYERS: frozenset[str] = frozenset({
    "memory",
    "docs",
    "tasks",
    "metrics",
    "routing",
    "graph",
    "health",
    "learning",
    "audit",
})


# ---------------------------------------------------------------------------
# Success envelope
# ---------------------------------------------------------------------------

def ok(data: Any, *, meta: dict | None = None) -> str:
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
    for _diag in ("tokens_estimated", "truncated",
                  "truncated_results_from", "truncated_results_to"):
        existing_meta.pop(_diag, None)

    # Strip `meta` from the data dict so we can re-attach with diagnostics
    body = {k: v for k, v in data.items() if k != "meta"}

    # First serialization to estimate tokens (meta is the in-progress dict
    # referenced below; JSON reflects current state each dump).
    serialized = json.dumps(
        {"ok": True, "data": {**body, "meta": existing_meta}},
        indent=2,
        default=str,
    )
    existing_meta["tokens_estimated"] = max(1, len(serialized) // 4)
    existing_meta["truncated"] = False

    # Enforce token budget
    if len(serialized) > TOKEN_BUDGET_CHARS:
        body, existing_meta = _apply_token_budget(body, existing_meta)
        existing_meta["truncated"] = True
        serialized = json.dumps(
            {"ok": True, "data": {**body, "meta": existing_meta}},
            indent=2,
            default=str,
        )
        existing_meta["tokens_estimated"] = max(1, len(serialized) // 4)

    payload = {"ok": True, "data": {**body, "meta": existing_meta}}
    return json.dumps(payload, indent=2, default=str)


def _apply_token_budget(body: dict, meta: dict) -> tuple[dict, dict]:
    """Shrink `body` to fit TOKEN_BUDGET_CHARS by trimming `results` list."""
    results = body.get("results")
    if not isinstance(results, list) or not results:
        # Shape doesn't match the standard list-wrapper; leave it alone
        return body, meta

    original_n = len(results)
    for keep in range(original_n - 1, 0, -1):
        trimmed_body = {**body, "results": results[:keep]}
        probe = json.dumps(
            {"ok": True, "data": {**trimmed_body, "meta": meta}},
            indent=2,
            default=str,
        )
        if len(probe) <= TOKEN_BUDGET_CHARS:
            meta["truncated_results_from"] = original_n
            meta["truncated_results_to"] = keep
            return trimmed_body, meta

    # Even keeping one result is over budget — return a body with zero results
    # so the envelope is at least valid JSON.
    meta["truncated_results_from"] = original_n
    meta["truncated_results_to"] = 0
    return {**body, "results": []}, meta


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------

def fail(
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool | None = None,
) -> str:
    """Wrap an error in the canonical envelope.

    If `retryable` is not given it is inferred from the category:
    `transient` and `unavailable` default to True; everything else to False.
    Override when a specific call has better information.
    """
    if retryable is None:
        retryable = category in _RETRYABLE_BY_DEFAULT
    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": category,
                "retryable": retryable,
                "message": message,
            },
        },
        indent=2,
        default=str,
    )


def safe_tool(fn: Callable[..., str]) -> Callable[..., str]:
    """Decorator: convert unhandled exceptions inside a tool to `fail()`.

    Mapping is conservative — specific Python exception types map to the
    closest envelope category; anything unrecognized becomes `internal`.
    Place this INSIDE `@mcp.tool(...)` so MCP still sees a string return:

        @mcp.tool(name="cos_example", ...)
        @safe_tool
        def cos_example(...) -> str:
            ...
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except PermissionError as exc:
            logger.exception("tool %s raised PermissionError", fn.__name__)
            return fail("permission", str(exc) or "permission denied", retryable=False)
        except FileNotFoundError as exc:
            logger.exception("tool %s raised FileNotFoundError", fn.__name__)
            return fail("not_found", str(exc) or "resource not found", retryable=False)
        except (TimeoutError, ConnectionError) as exc:
            logger.exception("tool %s raised transient error", fn.__name__)
            return fail("transient", str(exc) or type(exc).__name__, retryable=True)
        except ValueError as exc:
            logger.exception("tool %s raised ValueError", fn.__name__)
            return fail("validation", str(exc) or "invalid input", retryable=False)
        except ImportError as exc:
            logger.exception("tool %s raised ImportError", fn.__name__)
            return fail("unavailable", str(exc) or "optional dependency missing", retryable=True)
        except Exception as exc:  # noqa: BLE001 — last-resort envelope, never let tracebacks leak
            logger.exception("tool %s raised unexpected %s", fn.__name__, type(exc).__name__)
            return fail("internal", f"{type(exc).__name__}: {exc}", retryable=False)

    return wrapper
