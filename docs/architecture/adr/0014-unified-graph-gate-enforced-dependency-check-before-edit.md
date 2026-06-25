<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-25 -->
# ADR-0014: Unified graph-gate — a verifiable, consumer-facing dependency check before edits

> Nav: [ADR Index](./00-index.md)

## Status

Accepted (2026-06-25, epic `graph-first-enforcement`) — design firm. Implemented in clusters: C1 marker contract, C2 consumer scope, C3 tool usability, C4 hook consolidation ship first; C5 cross-adapter parity and C6 severity/hub/learning/i18n/xss follow.

- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** graph-first, enforce-graph-context, enforce-skill, marker-contract, freshness, rule-11, rule-23, consumer-parity, raptor-consolidation

## Context

A verified 35-item audit (graph-walk + adversarial red-team + completeness critic) found that the "consult the graph before editing load-bearing code" discipline is **taught but not enforced**, and for a **consumer project it ships pre-disabled**. The agent only ever consults dependencies when the *prompt* already sounds structural (the `nudge-graph-os.sh` prompt-wording trigger) — never because an *edit* forced it. The root causes, all confirmed against ground truth:

1. **Forgeable, self-attested markers.** [enforce-graph-context.sh](../../../src/core/hooks/enforce-graph-context.sh) passes on a `.graph-context-<sha1(path)>` marker, but the MCP tools ([graph.py](../../../src/core/graph_os/tools/graph.py) `_touch_session_marker`) write only `.graph-call-seen`. A real `cos_graph_context` call does **not** clear the hook; only a hand-run `write-state.sh` does. `cos_graph_rename_plan` writes no marker at all. The pass condition is a token the agent forges, decoupled from whether the graph was ever consulted (audit A1, A2, D2).
2. **Wrong obligation.** The hook demands `cos_graph_context` (neighbors), never `cos_graph_impact`/`cos_graph_references` (blast radius) — a context *read*, not a dependency *check* (audit C1).
3. **No freshness.** Markers carry no TTL / `content_hash` / index epoch, are written to `$COS_AGENT_DIR` (not panel-scoped), and are in **no GC sweep** — a single consult in session 1 licenses edits to that file in session 50 (audit C4, SM1). No query tool compares disk hash to index hash, so a just-edited symbol returns a confident blast radius from stale code (audit N3, N4).
4. **Consumers inert by construction.** `graph.enforce_context_on` ships `[]` in [_base scaffold](../../../src/templates/_base/scaffold/.coding-os/rag-config.yaml) and no stack overlay populates it, so the glob-gated hooks no-op on every consumer edit; no `graph-first` rule ships to consumers; `graph-explorer` maps to zero consumer globs; `enforce-skill.sh`'s graph requirement is gated behind a hardcoded `*core/*.py|*cli/*.py|*adapters/*.py` literal (Rule 11 violation) + `_in_meta_source_tree`, so consumers self-skip (audit B1–B5, D3).
5. **All warn, never block, no severity.** Every edit-time graph hook defaults to warn; blocking is opt-in env vars off by default; a 162-dependent chokepoint and a leaf file are treated identically (audit C2, D1, D4).
6. **Parasitic sprawl.** Four enforcement hooks + `verify-rename-callers` + `nudge-graph-os` + two reindex hooks and **four** marker schemes implement one concern; the two reindex hooks race on the same `rm`/`mv` tokens (audit N10).
7. **Cross-adapter blind.** Codex (Bash-only hook caps) silently renders none of the Write/Edit/Read gates ([hook_renderer.py](../../../src/cli/hook_renderer.py) drops them with no log), so a Codex session edits load-bearing files with zero graph consultation; the discipline does not travel with cross-adapter delegation (audit N1, N2).
8. **Tool usability pushes the agent back to grep.** `references` `count` lies (pre-trim length) with no pagination so a high-fan-in set is unretrievable; `cos_graph_impact` `visit_limit` is unreachable from the MCP schema though the HTTP route exposes it up to 50000 (a producer-with-two-consumers parity inversion — the Hub is more powerful than the agent); `dead_code` false-positives exception/PEP604-union/dynamic-dispatch classes; three disagreeing truncation signals (audit N5, N6, N12, N13, SM3).
9. **Shipped-but-broken correctness.** Harakat folding is query-side only — the FTS index is never folded, so Persian/Arabic symbols are permanently unfindable, and the one bench is harakat-free so it green-lights the break (audit SM4, TASK-485). Export-label XSS safety rests entirely on an unverified "no HTML sink exists today" assumption with zero adversarial test (audit SM5, TASK-486).

These are not nine subsystems to grow — they are **one concern implemented redundantly and left disabled**. The fix philosophy is Raptor-1→3: consolidate, make zero-overhead, eliminate parasitic complexity (Rule 22).

## Decision

Collapse "consult-before-edit" into **one graph-gate with markers the MCP layer writes**, so the marker is *proof of consultation*, not self-attestation; make it consumer-facing, freshness-bound, severity-graded, and adapter-portable. Six steps, each a deletion-heavy change.

### 1. Marker contract — machine-written, freshness-bound, one namespace, GC'd

Extend the proven `_touch_session_marker` pattern (~5 lines each): `cos_graph_context(target)` and `cos_graph_rename_plan(uid)` write their own marker under one `$COS_PANEL_DIR/.graph/` namespace (`ctx-<sha>`, `plan-<old>`, plus the existing `seen`), **embedding the consulted target's `content_hash` + index epoch**. The hook stops emitting any "now hand-run `write-state.sh`" instruction — there is nothing left to forge. A marker is **invalid when the file's current `content_hash` ≠ the recorded one** (kills the freshness hole). The single panel-scoped namespace gets one SessionStart GC + an mtime sweep (kills the immortal-marker leak). Query envelopes (`impact`/`context`/`references`/`detect_changes`) gain a `meta.stale` / freshness field comparing disk hash to `file_index_state`; an unindexed/just-created file reports `unindexed`, never a false "0 dependents = safe".

### 2. One hook, event-keyed

Merge `enforce-graph-context` (Write|Edit) + `enforce-graph-first-read` (Read) + `enforce-rename-plan` (Edit) + `verify-rename-callers` (PostToolUse Edit) into one `graph-gate.sh` registered on `PreToolUse Read|Write|Edit` + `PostToolUse Edit`, branching on `tool_name`. The load-bearing glob-match helper and the rename heuristic each run **once**, not copy-pasted across four files. `registry.yaml` stays the single registration SSOT.

### 3. Data-driven scope (delete the bash hardcode)

Delete the hardcoded `*core/*.py|*cli/*.py|*adapters/*.py` literal + `_in_meta_source_tree` + `_graph_module_disabled` from `enforce-skill.sh` (Rule 11). Render the graph-skill requirement from the `stack.yaml` SSOT like every other skill row. Populate `graph.enforce_context_on` in stack overlays (or derive it from the centrality cache, step 4) so consumer projects stop being inert; ship a stack-agnostic `graph-first` rule into `_base`; map `graph-explorer` as a consumer-stack secondary.

### 4. Centrality-graded severity, zero hot-path cost

At reindex time (the graph already reindexes), precompute a flat guard-set + per-node impact summary into a local cache. `graph-gate.sh` reads the **local cache** (file/SQLite read, no MCP round-trip) to grade: a high-fan-in node **blocks** by default, a leaf **warns**. A `cos_graph_centrality`/`impact` call is **never** wired synchronously into the Write/Edit hot path (two whole-graph `GROUP BY` scans per save is the latency cliff). A micro-bench latency ceiling on the PreToolUse chain locks the zero-overhead invariant.

### 5. Cross-adapter parity via a capability layer

Codex fires Bash PreToolUse: add a Bash-mediated graph-gate delegate that parses the target path out of `apply_patch`/`sed`/`tee`. Turn `hook_renderer.py`'s silent `if rendered_matcher is None: continue` into a tracked **parity-deficit report** so a dropped gate is visible, not silent. For auto-delegation, the dispatcher forwards `allowed_tools` and prepends a non-optional "`cos_graph_context` before any Edit" preamble, and `cos_supervise_record_output` verifies the `.graph/` marker for each load-bearing path the sub-agent touched.

### 6. Stays separate (anti-over-reach)

`auto-reindex-docs`, `warn-graph-empty`, `nudge-graph-os` are a different concern (freshness/indexing/prompt-nudge), share no marker, and folding them into graph-gate is over-reach. Only `auto-reindex-shell-ops` + `auto-prune-deleted-files` merge — into one ordered `auto-graph-reconcile-shell.sh` (tokenize once, **prune-if-gone THEN reindex-if-present**, fixing the N10 race). `nudge-graph-os` keeps its prompt-time value but points its debounce at the unified `.graph/` namespace.

**Net moving parts: 8 graph hooks → 5; 4 marker schemes → 1 machine-written namespace; minus ~25 lines of dead bash; plus ~10 lines of MCP marker-write.**

### Cluster → audit-item map

| Cluster | Closes | Swimlane |
|---|---|---|
| C1 marker contract + freshness + GC + producer test | A1, A2, C3, C4, D2, SM1, SM2 | graph_os |
| C2 consumer scope + data-driven (delete hardcode) | B1, B2, B3, B4, B5, D3 | core |
| C3 tool usability | N5, N6, N12, N13, SM3 | graph_os |
| C4 hook consolidation + reconcile + migration | N10, 4→1 merge, D3 render, SM6 | core |
| C5 cross-adapter parity | N1, N2, N11 | core |
| C6 severity cache + hub + learning + i18n + xss + test-dead-zone | D1, D4, N7, N8, N9, SM4, SM5, B6 | core |

## Backward-compat & consumer migration (SM6)

The hooks and markers ship into **every consumer** via live symlinks ([Modularity Map](../../../CLAUDE.md): `src/core/hooks/*.sh` → ALL consumers) and golden templates. Renaming hooks and the marker namespace is therefore a breaking change to every installed project at once. The migration is mandatory and explicit:

1. **Golden regen is part of C4, not a follow-up** — `make regen-adapter-templates` + golden re-render in the same change; `tests/test_adapter_parity.py` asserts no consumer breakage.
2. **One-shot old-marker sweep** — a SessionStart step removes the legacy `$COS_AGENT_DIR/.graph-context-*` / `.rename-plan-*` files so a consumer carrying old-namespace state is not spuriously re-blocked; absence of a marker simply means "consult again," which is the safe default.
3. **Default mode unchanged on upgrade** — consumers stay at warn by default; block is reserved for centrality-graded high-fan-in nodes and is opt-in per project, so an upgrade never mass-breaks existing consumer edits.
4. **Producer-side round-trip test is the C1 acceptance gate** (SM2) — a test that calls the MCP tool and asserts the marker exists, so a future regression that stops writing it cannot pass with green CI.

## Consequences

- **Positive:** a real, verifiable dependency check before load-bearing edits, on by default for consumers, that the agent cannot satisfy by forging a token; fewer moving parts than today (deletion-heavy).
- **Positive:** the freshness field closes the "stale graph reads as safe-to-change" trap, the most dangerous failure mode.
- **Positive:** Rule 11 literal removed from bash; scope becomes data-driven and regression-resistant.
- **Negative / cost:** the marker-contract change touches the producer (graph.py) and every consumer's hook namespace at once — paid down by the C4 migration + parity test; must land atomically with golden regen (Rule 10).
- **Negative / risk:** centrality-graded blocking can over-block if the cache miscalibrates; mitigated by warn-default + block only above a tuned fan-in threshold, and by keeping the grading off the synchronous path.
- **Deferred:** auto-tuning `enforce_context_on` from topology is **propose-not-apply only** (a human-approved review queue), never an auto-config-rewrite (N9) — speculative over-reach otherwise.
- **Limitation — Codex edit-isolation:** as with [ADR-0013](./0013-pr-mode-multi-agent-git-workflow-consumer-only.md), the Bash-mediated delegate narrows the gap but cannot match Claude's native Write/Edit hook fidelity; it is a capability limitation bounded by `adapter.yaml::hook_capabilities`, surfaced (not hidden) by the parity-deficit report.

## Alternatives Considered

- **Keep four hooks, just fix the markers.** Rejected: leaves the duplicated readlink/config preamble and four marker schemes — the parasitic complexity the Raptor lens targets; one event-keyed hook is fewer parts and one marker contract.
- **Wire `cos_graph_impact` synchronously into the edit hook for live severity.** Rejected: two whole-graph scans per save is a latency cliff (N7); a reindex-time cache delivers the same grading at zero hot-path cost.
- **Auto-populate `enforce_context_on` from centrality automatically.** Rejected as default: silent auto-config-rewrite is speculative and surprising; propose-not-apply keeps a human in the loop.
- **Make blocking the default everywhere.** Rejected: mass-breaks existing consumers on upgrade and blocks leaf-file edits with no blast radius; severity-graded block (high fan-in only) + warn-default is the calibrated middle.
