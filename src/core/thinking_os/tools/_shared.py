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

# OOM-safety ceiling for graph-export-shaped responses ({nodes, edges}).
# Rationale: structural snapshots aren't textual prose — they describe
# a whole subgraph. The agent-context budget (32 KB) is the wrong cap;
# the caller already constrained volume via max_nodes/max_hops (G35
# hard-caps max_nodes at 2000). UI consumers (/api/graph/export) need
# the full tree to render the CONTAINS spine. Set ceiling at ~5 MB —
# any browser fetches that comfortably, MCP transports tolerate it, and
# the full repo tree (1094 nodes + 1444 edges ≈ 1 MB with indent=2)
# never trips it under normal operation. Above the ceiling we fall
# back to coherent-subgraph trim (top-K nodes by degree, edges between
# kept nodes) so a pathological agent request never returns zero edges
# or an incoherent slice.
GRAPH_SUBGRAPH_BUDGET_CHARS = 5_000_000

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


def ok(data: Any, *, meta: dict | None = None, apply_budget: bool = True) -> str:
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
    # S11 (TASK-259): wide-payload tool list keys that were OUTSIDE the ladder,
    # so an oversized agent call produced envelope_unshrinkable — the same bug
    # class as the board 186KB ERROR, generalized. Adding a new wide tool? Add
    # its list key here (and to test_envelope.py::TestTrimLadderCoverage).
    "rows",  # cos_log_query, cos_metric_query, cos_audit_log_query
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


def _estimate_tokens(text: str) -> int:
    # Heuristic, NOT a tokenizer. chars/4 holds for ASCII but undercounts non-Latin
    # ~2-3x — BPE emits more tokens per char for CJK / Arabic / Cyrillic, so the old
    # chars/4 let oversized non-Latin payloads slip under the budget with
    # truncated=False (the coverage signal the graph-first contract trusts). Model:
    # ASCII ~4 chars/token; each non-ASCII char weighted ~1 token — heavier than
    # chars/4, which closes most of the gap. Not exact: dense CJK can still exceed
    # 1 tok/char (mild residual undercount) and Arabic/Cyrillic run lighter (mild
    # over-trim). The goal is removing the silent undercount, not matching a tokenizer.
    ascii_chars = len(text.encode("ascii", "ignore"))
    non_ascii = len(text) - ascii_chars
    return max(1, int(ascii_chars / 4 + non_ascii))


def _budget_size(text: str) -> int:
    # Token-normalised size for the char-denominated budgets: identical to len()
    # for ASCII (zero behaviour change), inflated for non-Latin so the trimmers
    # shrink to the real token budget instead of a char proxy.
    return max(len(text), _estimate_tokens(text) * 4)


def _probe_size(body: dict, meta: dict) -> int:
    return _budget_size(
        json.dumps(
            {"ok": True, "data": {**body, "meta": meta}},
            indent=2,
            default=str,
        )
    )


def _trim_list_key(body: dict, meta: dict, key: str) -> tuple[dict, dict, bool]:
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
    return body, meta, _probe_size(body, meta) <= TOKEN_BUDGET_CHARS


def _trim_coherent_subgraph(
    body: dict, meta: dict, *, budget_chars: int = TOKEN_BUDGET_CHARS
) -> tuple[dict, dict, bool]:
    """Coherent shrink for cos_graph_export-shaped responses.

    Strategy: binary-search the largest K such that the top-K nodes by
    incident-degree, plus the subset of edges that connect kept nodes,
    fit ``budget_chars``. Dropping nodes proportionally (instead of
    edges-first then nodes-first) keeps the subgraph connected — the
    Hub UI receives a coherent tree it can render, not 0 edges or 0
    nodes.

    ``budget_chars`` defaults to TOKEN_BUDGET_CHARS (32 KB). Graph-
    export callers pass GRAPH_SUBGRAPH_BUDGET_CHARS (≈500 KB) so the
    UI gets the full repo tree under normal load and only the most
    pathological agent requests trip the coherent trim.
    """
    nodes = body.get("nodes")
    edges = body.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return body, meta, _probe_size(body, meta) <= budget_chars
    if not nodes or not edges:
        return body, meta, _probe_size(body, meta) <= budget_chars

    # Degree map: edges that reference each uid.
    degree: dict[str, int] = {}
    for e in edges:
        if isinstance(e, dict):
            src = e.get("source_uid") or e.get("src_uid") or e.get("source")
            dst = e.get("target_uid") or e.get("dst_uid") or e.get("target")
            if src:
                degree[src] = degree.get(src, 0) + 1
            if dst:
                degree[dst] = degree.get(dst, 0) + 1

    def _uid_of(n):
        return n.get("uid") if isinstance(n, dict) else None

    # Sort nodes once: highest degree first, stable order for ties.
    nodes_sorted = sorted(
        nodes,
        key=lambda n: (-degree.get(_uid_of(n) or "", 0), nodes.index(n)),
    )
    original_n = len(nodes_sorted)
    original_e = len(edges)

    def _probe(k_nodes: int) -> tuple[list, list, int]:
        kept_nodes = nodes_sorted[:k_nodes]
        kept_uids = {_uid_of(n) for n in kept_nodes if _uid_of(n)}
        kept_edges = [
            e
            for e in edges
            if isinstance(e, dict)
            and (
                (e.get("source_uid") or e.get("src_uid") or e.get("source")) in kept_uids
                and (e.get("target_uid") or e.get("dst_uid") or e.get("target")) in kept_uids
            )
        ]
        trial = {**body, "nodes": kept_nodes, "edges": kept_edges}
        return kept_nodes, kept_edges, _probe_size(trial, meta)

    lo, hi = 0, original_n
    best_k = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        _, _, size = _probe(mid)
        if size <= budget_chars:
            best_k = mid
            lo = mid
        else:
            hi = mid - 1

    kept_nodes, kept_edges, _ = _probe(best_k)
    did_trim = best_k < original_n or len(kept_edges) < original_e
    if did_trim:
        meta["truncated_subgraph"] = True
        meta["truncated_nodes_from"] = original_n
        meta["truncated_nodes_to"] = best_k
        meta["truncated_edges_from"] = original_e
        meta["truncated_edges_to"] = len(kept_edges)
        body = {**body, "nodes": kept_nodes, "edges": kept_edges}
    return body, meta, did_trim


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


def _trim_nested_buckets(body: dict, meta: dict, parent_key: str) -> tuple[dict, dict, bool]:
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


# Scalars shorter than this are load-bearing (scope, risk_level, status,
# …) and can never recover meaningful budget — truncating a 4-char "high"
# is pure signal loss. The F#5 safety-net skips them and only shortens
# genuinely large scalars (signatures, generated text, big blobs).
_SCALAR_TRIM_FLOOR_CHARS = 200


def _trim_huge_string_fields(body: dict, meta: dict) -> tuple[dict, dict, bool]:
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


def _trim_lists_balanced(body: dict, meta: dict) -> tuple[dict, dict, bool]:
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


def _apply_token_budget(body: dict, meta: dict) -> tuple[dict, dict, bool]:
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


def validate_min_chars(value: Any, field: str, *, min_chars: int = 2) -> str | None:
    # W7.1 / R4-09: parity between cos_graph_query (already enforces 2)
    # and cos_graph_resolve (silently accepted single-char fuzzy).
    if not isinstance(value, str):
        return fail("validation", f"{field} must be a string (got {type(value).__name__})")
    if len(value.strip()) < min_chars:
        return fail("validation", f"{field} must be at least {min_chars} chars (got {value!r})")
    return None


def validate_confidence(value: Any, field: str) -> str | None:
    # W7.1 / R4-19/R4-26: confidence scores live in [0.0, 1.0]; the
    # cos_graph_impact / cos_graph_query tools silently accepted 999
    # and filtered everything.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fail("validation", f"{field} must be a number (got {type(value).__name__})")
    if value < 0.0 or value > 1.0:
        return fail("validation", f"{field} must be in [0.0, 1.0] (got {value})")
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
            result = fn(*args, **kwargs)
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

        # Name the offending tool when ok() flagged the envelope unshrinkable.
        # ok() logs the size from a context without the tool name, leaving the
        # eye with an unactionable "something is 265KB" error.
        if isinstance(result, str) and "envelope_unshrinkable" in result:
            logger.error(
                "tool %s returned an unshrinkable envelope (%d chars > %d budget)",
                fn.__name__,
                len(result),
                TOKEN_BUDGET_CHARS,
            )
        return result

    return wrapper
