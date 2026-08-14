"""MCP envelope — the trim ladder that shrinks an oversized response to budget.

`_apply_token_budget` is the orchestrator; everything above it is one rung.
The order is deliberate and widest-signal-first: nested member lists, then
dict-of-list buckets, then a balanced multi-bucket pass, then the per-key list
ladder, then `edges_by_type`, and only last the huge-scalar safety net —
because each later rung destroys more of the caller's answer than the one
before it. Every rung records `truncated_<key>_from`/`_to` in `meta` so an
agent can tell a trimmed list from a genuinely empty one; a rung that drops
items without leaving a marker is the bug class this ladder exists to prevent.

Graph-export-shaped payloads never reach here — `ok()` routes them to
`_envelope_subgraph`, whose connectivity invariant the ladder cannot honour.
"""

from __future__ import annotations

import logging
from typing import Any

try:  # package import
    from ._envelope_size import TOKEN_BUDGET_CHARS, _probe_size
except ImportError:  # flat import
    from _envelope_size import (  # type: ignore[no-redef,import-not-found]
        TOKEN_BUDGET_CHARS,
        _probe_size,
    )

logger = logging.getLogger("coding_os.tools._shared")

# keys that hold list payloads across cos_* tools. Trimmer
# walks them in order — biggest payload first when there's a choice.
# `results` stays first for legacy callers; context/references/impact
# emit the rest. `edges_by_type` is a dict-of-lists handled separately.
_TRIMMABLE_LIST_KEYS: tuple[str, ...] = (
    "results",
    "neighbours",
    "references",
    # Export-shaped responses — trim `edges` BEFORE `nodes`.
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
    # cos_graph_detect_changes bulk arrays.
    "symbols",
    "downstream_consumers",
    "downstream_tasks",
    # S11: wide-payload tool list keys that were OUTSIDE the ladder,
    # so an oversized agent call produced envelope_unshrinkable — the same bug
    # class as the board 186KB ERROR, generalized. Adding a new wide tool? Add
    # its list key here (and to test_envelope.py::TestTrimLadderCoverage).
    "rows",  # cos_log_query, cos_metric_query
    "entries",  # cos_timeline
    "cycles",  # cos_graph_cycles
    "untested",  # cos_graph_test_gap
    "dead",  # cos_graph_dead_code
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
_TRIMMABLE_NESTED_MEMBERS: tuple[tuple[str, str], ...] = (("processes", "members"),)

# Scalars shorter than this are load-bearing (scope, risk_level, status,
# …) and can never recover meaningful budget — truncating a 4-char "high"
# is pure signal loss. The F#5 safety-net skips them and only shortens
# genuinely large scalars (signatures, generated text, big blobs).
_SCALAR_TRIM_FLOOR_CHARS = 200


def _trim_list_key(
    body: dict[str, Any], meta: dict[str, Any], key: str
) -> tuple[dict[str, Any], dict[str, Any], bool]:
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
        # N5: a sibling `count` that mirrored the pre-trim list length would now
        # lie (count=100 while the array holds 60). Reconcile it through every
        # shrink step — but ONLY when it provably tracked THIS list (== original
        # length), never a count describing a different key.
        count_tracks_key = body.get("count") == original_n
        body = {**body, key: items[:best_keep]}
        if count_tracks_key:
            body["count"] = best_keep
        # The binary search probed fit with `meta` BEFORE these two marker
        # keys existed; committing them grows the envelope by ~50 bytes and
        # can push a borderline best_keep back over budget. Re-check the
        # committed body and shrink one element further until it truly fits,
        # so the ladder never returns a marginally-over body that then falls
        # through and mauls load-bearing scalars (scope/risk_level).
        while best_keep > 0 and _probe_size(body, meta) > TOKEN_BUDGET_CHARS:
            best_keep -= 1
            meta[f"truncated_{key}_to"] = best_keep
            body = {**body, key: items[:best_keep]}
            if count_tracks_key:
                body["count"] = best_keep
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _trim_edges_by_type(
    body: dict[str, Any], meta: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], bool]:
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
    while (
        _probe_size({**body, "edges_by_type": {**non_list, **list_buckets}}, meta)
        > TOKEN_BUDGET_CHARS
    ):
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
    body: dict[str, Any], meta: dict[str, Any], parent_key: str
) -> tuple[dict[str, Any], dict[str, Any], bool]:
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
    while (
        _probe_size({**body, parent_key: {**non_list, **list_buckets}}, meta) > TOKEN_BUDGET_CHARS
    ):
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
    body: dict[str, Any],
    meta: dict[str, Any],
    parent_key: str,
    member_key: str,
    *,
    floor: int = 3,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
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
    # iter_guard caps the halving loop. Each iteration halves the
    # biggest member list above `floor`, so at most ceil(log2(max_len))
    # passes per entry × N entries. 64 covers up to ~2^64 starting size
    # while keeping the loop bounded against pathological inputs.
    _ITER_GUARD_MAX = 64
    while (
        _probe_size({**body, parent_key: new_items}, meta) > TOKEN_BUDGET_CHARS
        and iter_guard < _ITER_GUARD_MAX
    ):
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
    body: dict[str, Any], meta: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], bool]:
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
        if len(v) < _SCALAR_TRIM_FLOOR_CHARS:
            # Tiny load-bearing scalar (scope/risk_level/status) — truncating
            # it can't recover budget and destroys signal. Leave intact.
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


def _trim_lists_balanced(
    body: dict[str, Any], meta: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    # F1: balanced multi-bucket trim. When >=2 trimmable list keys are
    # present, shrink the LARGEST remaining list repeatedly (never below 1
    # item) until the envelope fits — so no bucket is silently zeroed while
    # a sibling bucket keeps items. Root cause of cos_graph_contracts(
    # kinds=http,mcp) returning http_routes=[] while mcp_tools kept 70:
    # the sequential ladder drained http_routes (earlier key) to 0 because
    # mcp_tools (later key) alone exceeded the budget. Uses the same
    # truncated_<key>_from/to markers as the per-key ladder so coverage
    # flags stay consistent. No-op (and identical to the old path) when
    # fewer than two list buckets are present.
    present = [
        k for k in _TRIMMABLE_LIST_KEYS if isinstance(body.get(k), list) and len(body[k]) > 0
    ]
    if len(present) < 2:
        return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    originals = {k: len(body[k]) for k in present}
    while _probe_size(body, meta) > TOKEN_BUDGET_CHARS:
        biggest = max(present, key=lambda x: len(body[x]))
        cur_n = len(body[biggest])
        if cur_n <= 1:
            break  # every bucket down to its last survivor — fall through
        new_n = max(1, int(cur_n * 0.85))
        if new_n >= cur_n:
            new_n = cur_n - 1
        body = {**body, biggest: body[biggest][:new_n]}
    for k in present:
        kept = len(body[k])
        if kept < originals[k]:
            meta[f"truncated_{k}_from"] = originals[k]
            meta[f"truncated_{k}_to"] = kept
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _apply_token_budget(
    body: dict[str, Any], meta: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    # Trim every list-shaped field + edges_by_type dict-of-lists + (F#5
    # final safety net) huge non-list scalars. did_trim=True when any
    # field got cut. Contract: post-trim body MUST fit budget — if even
    # scalar truncation fails (extreme pathological case), surface via
    # meta.envelope_unshrinkable=True so caller can log/alert.
    # Graph-subgraph shape ({nodes,edges}) is handled by ok() ahead of
    # this call via _trim_coherent_subgraph, so the per-key trim ladder
    # below never zeroes out edges.
    did_any = False
    fits = _probe_size(body, meta) <= TOKEN_BUDGET_CHARS
    # W6.2: shrink nested members (processes[*].members) BEFORE dropping
    # whole entries — preserves community/process count signal.
    for parent_key, member_key in _TRIMMABLE_NESTED_MEMBERS:
        if fits:
            break
        body, meta, fits_after = _trim_nested_member_lists(body, meta, parent_key, member_key)
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
    # F1: balanced multi-bucket trim BEFORE the sequential per-key ladder,
    # so an earlier bucket isn't zeroed while a larger later bucket keeps
    # items. No-op for single-bucket payloads (the ladder below handles
    # those unchanged).
    if not fits:
        _markers_before = sum(1 for k in meta if k.startswith("truncated_") and k.endswith("_to"))
        body, meta, fits = _trim_lists_balanced(body, meta)
        _markers_after = sum(1 for k in meta if k.startswith("truncated_") and k.endswith("_to"))
        if _markers_after > _markers_before:
            did_any = True
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
        # Debug-level here; the @safe_tool layer re-logs this at ERROR WITH the
        # tool name so the eye gets an actionable, deduplicable row
        # instead of an anonymous one. Tools not wrapped by safe_tool are rare.
        logger.debug(
            "envelope %d chars > budget %d after all trims",
            _probe_size(body, meta),
            TOKEN_BUDGET_CHARS,
        )
        did_any = True
    return body, meta, did_any
