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
    # W6.6 (B4): export-shaped responses — trim `edges` BEFORE `nodes`.
    # Caller asked for nodes; edges are the high-volume tail.
    "edges",
    "nodes",
    "processes",
    "call_sites",
    "import_sites",
    "doc_references",
    "test_references",
    "string_literals",
    "external_targets",
    "branches",
    "steps",
    # W6.2: cos_graph_contracts top-level buckets.
    "http_routes",
    "mcp_tools",
    "grpc_endpoints",
    "event_handlers",
    "websocket",
    # Common list payloads in other tools.
    "nodes_top",
    "samples",
)

# W6.2: dict-of-lists buckets (parent_key → {sub_key: [items]}). Trimmer
# halves the biggest sub-list until envelope fits, like _trim_edges_by_type.
# Covers cos_graph_impact.tiers + cos_graph_contracts.* bucketed outputs.
_TRIMMABLE_NESTED_BUCKETS: tuple[str, ...] = (
    "tiers",
    "http_routes_by_method",
    "mcp_tools_by_module",
    "event_handlers_by_source",
    "contracts",
)

# W6.2: list[dict] containers whose members carry a nested list to trim.
# (parent_key, member_list_key) — e.g. ("processes", "members") for
# cos_graph_communities so we shrink members per-process before dropping
# whole processes.
_TRIMMABLE_NESTED_MEMBERS: tuple[tuple[str, str], ...] = (
    ("processes", "members"),
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
    # Binary-search shrink the list at body[key] until envelope ≤ budget.
    # Returns (body, meta, fits). O(log N) probes.
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
    # edges_by_type is dict-of-lists; greedily halve biggest bucket until fits.
    edges_by_type = body.get("edges_by_type")
    if not isinstance(edges_by_type, dict) or not edges_by_type:
        return body, meta, False
    # F#6: separate list buckets (trimmable) from non-list values (preserved).
    list_buckets = {k: list(v) for k, v in edges_by_type.items() if isinstance(v, list)}
    non_list = {k: v for k, v in edges_by_type.items() if not isinstance(v, list)}
    if not list_buckets:
        return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    trim_record: dict[str, dict[str, int]] = {}
    while _probe_size(
        {**body, "edges_by_type": {**non_list, **list_buckets}}, meta
    ) > TOKEN_BUDGET_CHARS:
        biggest = max(list_buckets, key=lambda k: len(list_buckets[k]), default=None)
        if biggest is None or not list_buckets[biggest]:
            break
        before = trim_record.get(biggest, {}).get("from", len(edges_by_type[biggest]))
        new_len = max(0, len(list_buckets[biggest]) // 2)
        trim_record[biggest] = {"from": before, "to": new_len}
        list_buckets[biggest] = list_buckets[biggest][:new_len]
        if all(len(v) == 0 for v in list_buckets.values()):
            break
    body = {**body, "edges_by_type": {**non_list, **list_buckets}}
    if trim_record:
        meta["truncated_edges_by_type"] = trim_record
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _trim_nested_buckets(
    body: dict, meta: dict, parent_key: str
) -> tuple[dict, dict, bool]:
    # W6.2: parent_key holds a dict mapping sub_key → list[items]
    # (impact.tiers, contracts.http_routes_by_method, etc). Same halve-
    # biggest strategy as _trim_edges_by_type.
    parent = body.get(parent_key)
    if not isinstance(parent, dict) or not parent:
        return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    list_buckets = {k: list(v) for k, v in parent.items() if isinstance(v, list)}
    non_list = {k: v for k, v in parent.items() if not isinstance(v, list)}
    if not list_buckets:
        return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    trim_record: dict[str, dict[str, int]] = {}
    original_lens = {k: len(v) for k, v in list_buckets.items()}
    while _probe_size(
        {**body, parent_key: {**non_list, **list_buckets}}, meta
    ) > TOKEN_BUDGET_CHARS:
        biggest = max(list_buckets, key=lambda k: len(list_buckets[k]), default=None)
        if biggest is None or not list_buckets[biggest]:
            break
        new_len = max(0, len(list_buckets[biggest]) // 2)
        trim_record[biggest] = {"from": original_lens[biggest], "to": new_len}
        list_buckets[biggest] = list_buckets[biggest][:new_len]
        if all(len(v) == 0 for v in list_buckets.values()):
            break
    body = {**body, parent_key: {**non_list, **list_buckets}}
    if trim_record:
        meta[f"truncated_{parent_key}"] = trim_record
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _trim_nested_member_lists(
    body: dict, meta: dict, parent_key: str, member_key: str, *, floor: int = 3
) -> tuple[dict, dict, bool]:
    # W6.2: shrink list-of-dict members[*]. e.g. processes[*].members.
    # Halve member-lists per-entry until envelope fits or floor reached;
    # then drop whole entries from the tail.
    items = body.get(parent_key)
    if not isinstance(items, list) or not items:
        return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    members_orig = [len(it.get(member_key) or []) if isinstance(it, dict) else 0 for it in items]
    new_items = [dict(it) if isinstance(it, dict) else it for it in items]
    record: dict[str, int] = {}
    iter_guard = 0
    while _probe_size({**body, parent_key: new_items}, meta) > TOKEN_BUDGET_CHARS and iter_guard < 64:
        iter_guard += 1
        # find entry with biggest member list above floor
        candidate_idx = -1
        biggest = floor
        for i, it in enumerate(new_items):
            if not isinstance(it, dict):
                continue
            n = len(it.get(member_key) or [])
            if n > biggest:
                biggest = n
                candidate_idx = i
        if candidate_idx == -1:
            break
        entry = new_items[candidate_idx]
        mlist = entry.get(member_key) or []
        new_len = max(floor, len(mlist) // 2)
        entry[member_key] = mlist[:new_len]
        record[f"entry_{candidate_idx}_{member_key}"] = new_len
    # If still over budget, drop tail entries.
    while (
        _probe_size({**body, parent_key: new_items}, meta) > TOKEN_BUDGET_CHARS
        and len(new_items) > 1
    ):
        new_items.pop()
        record["entries_dropped_tail"] = record.get("entries_dropped_tail", 0) + 1
    body = {**body, parent_key: new_items}
    if record:
        meta[f"truncated_{parent_key}_{member_key}"] = record
        meta[f"{parent_key}_original_member_counts"] = members_orig
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _trim_huge_string_fields(
    body: dict, meta: dict
) -> tuple[dict, dict, bool]:
    # F#5 safety net: after list trims, if envelope still over budget the
    # culprit is a huge top-level scalar (large signature, generated text).
    # Truncate biggest scalars first until envelope fits. Never touch
    # `node` (caller's root identity). W6.2: ONLY touch str fields —
    # numeric scalars (int/float/bool) preserve typed contract (e.g.
    # impacted_count must stay int). Strings get a cut-to-length prefix
    # instead of a sentinel so partial content remains useful.
    if _probe_size(body, meta) <= TOKEN_BUDGET_CHARS:
        return body, meta, True
    sizes: list[tuple[int, str]] = []
    for k, v in body.items():
        if k == "node" or isinstance(v, (list, dict)):
            continue
        if not isinstance(v, str):
            # W6.2 (T4/F7): never stringify int/bool/float scalars.
            continue
        sizes.append((len(v), k))
    if not sizes:
        return body, meta, False
    sizes.sort(reverse=True)
    truncated_fields: list[str] = []
    new_body = dict(body)
    for _size, key in sizes:
        if _probe_size(new_body, meta) <= TOKEN_BUDGET_CHARS:
            break
        original = new_body[key]
        # Aggressive halving until fits or string drops below 80 chars.
        cut = max(80, len(original) // 2)
        while cut > 0 and _probe_size(new_body, meta) > TOKEN_BUDGET_CHARS:
            new_body[key] = original[:cut] + "…[truncated]"
            cut //= 2
        truncated_fields.append(key)
    if truncated_fields:
        meta["truncated_string_fields"] = truncated_fields
    return new_body, meta, _probe_size(new_body, meta) <= TOKEN_BUDGET_CHARS


def _apply_token_budget(body: dict, meta: dict) -> tuple[dict, dict, bool]:
    # Trim every list-shaped field + edges_by_type dict-of-lists + (F#5
    # final safety net) huge non-list scalars. did_trim=True when any
    # field got cut. Contract: post-trim body MUST fit budget — if even
    # scalar truncation fails (extreme pathological case), surface via
    # meta.envelope_unshrinkable=True so caller can log/alert.
    did_any = False
    fits = _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    # W6.2: shrink nested members (processes[*].members) BEFORE dropping
    # whole entries — preserves community/process count signal.
    for parent_key, member_key in _TRIMMABLE_NESTED_MEMBERS:
        if fits:
            break
        body, meta, fits_after = _trim_nested_member_lists(
            body, meta, parent_key, member_key
        )
        if f"truncated_{parent_key}_{member_key}" in meta:
            did_any = True
        fits = fits or fits_after
    # W6.2: shrink dict-of-list buckets (impact.tiers, contracts.*) BEFORE
    # toplevel list trims so we preserve top-level metadata (impacted_count,
    # http_routes count etc).
    for parent_key in _TRIMMABLE_NESTED_BUCKETS:
        if fits:
            break
        body, meta, fits_after = _trim_nested_buckets(body, meta, parent_key)
        if f"truncated_{parent_key}" in meta:
            did_any = True
        fits = fits or fits_after
    for key in _TRIMMABLE_LIST_KEYS:
        if fits:
            break
        body, meta, fits_after = _trim_list_key(body, meta, key)
        if f"truncated_{key}_to" in meta:
            did_any = True
        fits = fits or fits_after
    if not fits:
        body, meta, fits_after = _trim_edges_by_type(body, meta)
        if "truncated_edges_by_type" in meta:
            did_any = True
        fits = fits or fits_after
    if not fits:
        body, meta, fits_after = _trim_huge_string_fields(body, meta)
        if "truncated_string_fields" in meta:
            did_any = True
        fits = fits or fits_after
    if not fits:
        meta["envelope_unshrinkable"] = True
        logger.error(
            "envelope %d chars > budget %d after all trims",
            _probe_size(body, meta),
            TOKEN_BUDGET_CHARS,
        )
        did_any = True
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
