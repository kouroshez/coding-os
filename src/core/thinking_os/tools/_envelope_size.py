"""MCP envelope — how big a response is, in the units the budgets use.

The measurement leaf. `_estimate_tokens` models the tokenizer; `_budget_size`
converts that model back into the char-denominated budget the trimmers compare
against; `_probe_size` measures a candidate body+meta pair without committing
it. Everything that shrinks a response asks these three how much it saved.

Separate from the trimmers because it changes for its own reason — a better
token model, or a re-sized budget — and because consumers outside this package
(board_os pre-flight sizing, the graph_os token-cost bench) import it directly
without wanting the ladder.
"""

from __future__ import annotations

import json
from typing import Any

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


def _probe_size(body: dict[str, Any], meta: dict[str, Any]) -> int:
    return _budget_size(
        json.dumps(
            {"ok": True, "data": {**body, "meta": meta}},
            indent=2,
            default=str,
        )
    )
