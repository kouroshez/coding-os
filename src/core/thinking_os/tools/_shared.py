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
from collections.abc import Callable
from functools import wraps
from typing import Any, Literal

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
        "audit",
    }
)


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
    existing_meta["tokens_estimated"] = max(1, len(serialized) // 4)
    existing_meta["truncated"] = False

    # Enforce token budget. `truncated` only flips when _apply_token_budget
    # actually shrank the body — a no-op (shape not matched) leaves the
    # flag False so agents trust the signal.
    if len(serialized) > TOKEN_BUDGET_CHARS:
        body, existing_meta, did_trim = _apply_token_budget(body, existing_meta)
        if did_trim:
            existing_meta["truncated"] = True
            serialized = json.dumps(
                {"ok": True, "data": {**body, "meta": existing_meta}},
                indent=2,
                default=str,
            )
            existing_meta["tokens_estimated"] = max(1, len(serialized) // 4)

    payload = {"ok": True, "data": {**body, "meta": existing_meta}}
    return json.dumps(payload, indent=2, default=str)


# TASK-034: keys that hold list payloads across cos_* tools. Trimmer
# walks them in order — biggest payload first when there's a choice.
# `results` stays first for legacy callers; context/references/impact
# emit the rest. `edges_by_type` is a dict-of-lists handled separately.
_TRIMMABLE_LIST_KEYS: tuple[str, ...] = (
    "results",
    "neighbours",
    "references",
    "nodes",
    "edges",
    "processes",
    "call_sites",
    "doc_references",
    "test_references",
    "string_literals",
)


def _probe_size(body: dict, meta: dict) -> int:
    return len(
        json.dumps(
            {"ok": True, "data": {**body, "meta": meta}},
            indent=2,
            default=str,
        )
    )


def _trim_list_key(
    body: dict, meta: dict, key: str
) -> tuple[dict, dict, bool]:
    """Halve the list at `body[key]` until envelope ≤ TOKEN_BUDGET_CHARS.

    Returns (body, meta, fits). `fits=True` means we're now under budget.
    Uses binary-search shrink so worst-case is O(log N) probes.
    """
    items = body.get(key)
    if not isinstance(items, list) or not items:
        return body, meta, False
    original_n = len(items)
    lo, hi = 0, original_n
    best_keep = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        trial = {**body, key: items[:mid]}
        if _probe_size(trial, meta) <= TOKEN_BUDGET_CHARS:
            best_keep = mid
            lo = mid
        else:
            hi = mid - 1
    if best_keep < original_n:
        meta[f"truncated_{key}_from"] = original_n
        meta[f"truncated_{key}_to"] = best_keep
        body = {**body, key: items[:best_keep]}
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _trim_edges_by_type(body: dict, meta: dict) -> tuple[dict, dict, bool]:
    """`edges_by_type` is a dict-of-lists. Trim biggest bucket first."""
    edges_by_type = body.get("edges_by_type")
    if not isinstance(edges_by_type, dict) or not edges_by_type:
        return body, meta, False
    # Greedy pick biggest bucket each iteration; halve it.
    trimmed = {k: list(v) for k, v in edges_by_type.items() if isinstance(v, list)}
    trim_record: dict[str, dict[str, int]] = {}
    while _probe_size({**body, "edges_by_type": trimmed}, meta) > TOKEN_BUDGET_CHARS:
        # Pick biggest bucket; halve.
        biggest = max(trimmed, key=lambda k: len(trimmed[k]), default=None)
        if biggest is None or not trimmed[biggest]:
            break
        before = trim_record.get(biggest, {}).get("from", len(edges_by_type[biggest]))
        new_len = max(0, len(trimmed[biggest]) // 2)
        trim_record[biggest] = {"from": before, "to": new_len}
        trimmed[biggest] = trimmed[biggest][:new_len]
        if all(len(v) == 0 for v in trimmed.values()):
            break
    body = {**body, "edges_by_type": trimmed}
    if trim_record:
        meta["truncated_edges_by_type"] = trim_record
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _apply_token_budget(body: dict, meta: dict) -> tuple[dict, dict, bool]:
    """Shrink `body` to fit TOKEN_BUDGET_CHARS.

    Strategy: trim every trimmable list-shaped field in order, plus the
    `edges_by_type` dict-of-lists. ``did_trim`` is True when any field
    actually got cut. Conservative — leaves non-list payloads untouched.
    """
    did_any = False
    fits = _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    for key in _TRIMMABLE_LIST_KEYS:
        if fits:
            break
        body, meta, fits_after = _trim_list_key(body, meta, key)
        if fits_after and not fits:
            did_any = True
        if f"truncated_{key}_to" in meta:
            did_any = True
        fits = fits or fits_after
    if not fits:
        body, meta, fits_after = _trim_edges_by_type(body, meta)
        if "truncated_edges_by_type" in meta:
            did_any = True
        fits = fits or fits_after
    return body, meta, did_any


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


# ---------------------------------------------------------------------------
# G36: SSOT validation helpers — uniform shape across all cos_* tools.
# Return None when valid, a fail-envelope string when invalid. Caller
# pattern is `err = validate_X(...); if err: return err`.
# ---------------------------------------------------------------------------


def validate_enum(value: Any, allowed: tuple[str, ...], field: str) -> str | None:
    # None when valid; fail envelope when value not in allowed.
    if value not in allowed:
        return fail(
            "validation",
            f"{field} must be one of {allowed} (got {value!r})",
        )
    return None


def validate_positive_int(value: Any, field: str) -> str | None:
    # Reject non-int / <=0; otherwise None.
    if not isinstance(value, int) or value <= 0:
        return fail("validation", f"{field} must be a positive int (got {value!r})")
    return None


def validate_non_empty_str(value: Any, field: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return fail("validation", f"{field} must be a non-empty string")
    return None


def clamp_int(value: int, *, min_v: int, max_v: int) -> tuple[int, bool]:
    # Return (clamped, was_clamped). Caller surfaces was_clamped in meta.
    clamped = max(min_v, min(value, max_v))
    return clamped, clamped != value


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
        except Exception as exc:
            logger.exception("tool %s raised unexpected %s", fn.__name__, type(exc).__name__)
            return fail("internal", f"{type(exc).__name__}: {exc}", retryable=False)

    return wrapper
