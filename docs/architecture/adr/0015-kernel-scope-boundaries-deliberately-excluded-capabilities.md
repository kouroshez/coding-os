<!-- domain:META | layer:adr | ssot:true | updated:2026-06-28 -->
---
title: "ADR-0015: Kernel scope boundaries — capabilities we deliberately will not build"
domain: META
layer: adr
status: accepted
updated: 2026-06-28
---

# ADR-0015: Kernel scope boundaries — capabilities we deliberately will not build

Purpose: Record the platform-grade capabilities the kernel will NOT grow — each with the value it would violate — so a future agent does not reintroduce them as an "obvious" addition.
Read when: scoping a large new subsystem, or evaluating a "we should add X" proposal that resembles a row below.
Skip when: the change is a bounded improvement to an existing subsystem.
Read next: [anti-overengineering.md](../../../src/core/rules/anti-overengineering.md) · [constitution.md](../../governance/constitution.md).

> Nav: [ADR Index](00-index.md) | [Docs Index](../../00-index.md)

## Status

Accepted (2026-06-28).

## Context

The kernel is a single-user, single-machine cognitive OS: one interactive agent, an embedded SQLite store, file-based state, and a FastMCP server. Several "platform-grade" capabilities look attractive in the abstract but are parasitic complexity at this scale — each is a permanent liability a future maintainer carries forever (constitution: every line is a cost; Rule 22: anti-overengineering). This ADR names the ones we have deliberately decided against, so the decision is explicit and not re-litigated every time one resurfaces.

## Decision — deliberately excluded (with the value each would violate)

| Capability | Why excluded |
|---|---|
| **Distributed consensus** (Raft / PBFT / gossip, multi-node coordination) | Single-machine by design; SQLite + `fcntl.flock` + `index.lock` retry already serialize the only real concurrency (sibling sessions). Consensus solves a problem we do not have. (minimal-context, anti-overengineering) |
| **Cross-machine federation / agent swarm** (peer discovery, remote actors) | No multi-host workload exists; dispatch is single-host, in-process ([dispatch-deferral ADR](../../governance/adr-role-dispatch-deferral.md)). Federation is speculation with zero caller. (no-speculation) |
| **A compiled / WASM rule kernel** | Rules are Markdown SSOT surfaced to the agent and enforced by fail-closed shell hooks. A compiled kernel adds a build step plus a second governance source-of-truth to keep in sync — drift risk for no latency need. (SSOT-first, P1) |
| **ANN / quantization vector indexes** (HNSW, RaBitQ, product quantization) | The corpus is thousands of rows, not millions; FTS5 bm25 + brute-force cosine answer in well under the budget. An ANN index is a second structure to build, tune, and keep consistent for a recall problem we do not have. (anti-overengineering) |
| **A second learning / vector store** (a separate embedded DB beside SQLite) | One store (SQLite + FTS5 + the sqlite-vec path) is the SSOT for memory, graph, board, and dispatch. A second store doubles the migration, backup, and drift surface. (SSOT-first) |
| **A multi-provider model facade** (a uniform shim over N LLM vendors) | The kernel dispatches through the real adapter SDKs (Claude `claude_agent_sdk`, Codex `codex exec`) — typed, capable substrates. A generic facade would be a thinner abstraction over richer ones; the cross-adapter need is met by `DispatchRequest.adapter` + the routing hint, not a vendor-agnostic wrapper. (P8 adapter-SDK autonomy, reuse-first) |

## Consequences

- These are **decisions, not deferred TODOs.** A proposal matching a row above is rejected by default; reopening one requires a concrete in-tree caller whose value cannot be met by the existing substrate — the Rule 22 "when refactoring/adding *is* justified" bar.
- The multi-model **autonomy** the kernel does pursue is cost-routing over the existing dispatch substrate ([dispatch-deferral ADR](../../governance/adr-role-dispatch-deferral.md), partially revived) — not a provider facade, not a swarm.
- The boundary is auditable: if one of these appears in the tree without a caller, it is dead weight to remove, and this ADR is the citation.

## References

- [src/core/rules/anti-overengineering.md](../../../src/core/rules/anti-overengineering.md) — the five sub-rules these derive from.
- [docs/governance/constitution.md](../../governance/constitution.md) — the values (minimal-context, SSOT-first).
- [adr-role-dispatch-deferral.md](../../governance/adr-role-dispatch-deferral.md) — the dispatch path (partially revived) these boundaries sit beside.
