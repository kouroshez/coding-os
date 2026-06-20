<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-19 -->

# ADR-0011: Cross-adapter orchestration lives in core; P8 is not the blocker

- **Status:** Proposed (2026-06-19, TASK-462) — seam named, deferred (Claude-only phase)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** adapters, cognition, dispatcher, model-routing, strategic-audit-2026-06

## Context

A stated product goal is **cross-adapter orchestration**: an agent mid-task hands
some work to Codex, some to a Sonnet session, some to an ops runner — using each
runtime/model where it is strongest. Two confusions surround this today, and the
strategic audit (2026-06-19) resolved both against the code:

1. **Cross-adapter handoff is conflated with model routing.** They are different
   layers. `model_routing` (ModelPicker, `routing.py`, `nudge-model-routing.sh`)
   chooses a **model tier within one adapter** (sonnet/opus/haiku inside Claude;
   the tier→id alias resolver lives in `src/adapters/claude/sdk_dispatcher.py`).
   Cross-**adapter** handoff (claude ↔ codex) is a separate capability and is
   **absent** — distinct from model routing being merely dormant.
2. **P8 is assumed to forbid it.** P8 ("never import an adapter SDK from
   `src/core/**`") is **not** the blocker. `src/core/thinking_os/dispatcher.py`
   already loads adapter dispatchers per agent by **file path via importlib**
   (`_try_load_adapter_dispatcher`, `spec_from_file_location`), so core stays
   free of static SDK imports while still being able to resolve *more than one*
   adapter. The plumbing for multi-adapter already exists.

The real and only blocker is a **deliberate invariant**: `get_dispatcher()`
treats `DispatchRequest.adapter` as a **hint** — on mismatch it logs a warning
and proceeds on the *session* adapter (`dispatcher.py:168-175`), and
`cos_dispatch_parallel_run` resolves **one** dispatcher and fans the same adapter
across all formulas (`cognition.py:1504`). The dispatcher contract names this
explicitly: *"adapter hint, not adapter switch … honoring the hint with a real
cross-adapter dispatch is the explicit follow-up seam"*
(`docs/engineering/dispatcher-contract.md:126-134`). The modularity audit
deliberately chose **"do NOT build cross-adapter dispatch now (Claude-only)"**
(`modularity-audit-2026-06.md:116`).

## Decision

**The cross-adapter orchestrator belongs in core, resolving a dispatcher
per-request; the single decision required to enable it is relaxing the
"one adapter per session" invariant. Defer the build — do not market it as a
current capability until it ships.**

1. **Home = core.** Orchestration logic (which task → which adapter/model) lives
   in `src/core/thinking_os/` and resolves a dispatcher **per `DispatchRequest`**
   via the existing importlib loader. No adapter SDK is imported into core; P8
   holds. Adapters stay pure translation layers.
2. **The one change of substance** is making `get_dispatcher()` honor a validated
   `adapter` per request (and `cos_dispatch_parallel_run` resolve a dispatcher
   *per formula*) instead of collapsing to the session adapter. Everything else
   (loader, envelope, presence) already supports it.
3. **Gate on capability + readiness, not ambition.** A target adapter is only
   eligible if its `adapter.yaml::hook_capabilities` and runtime support the work,
   and the empirical router (ADR-pending) has signal to justify the handoff.
   This depends on the degenerate-outcome fix (audit group B) — until outcomes
   carry real per-adapter/model signal, "route to the best adapter" has nothing
   to route on.

## Consequences

- **Positive:** the user's headline differentiator has a concrete, P8-compatible
  home and a *single* well-scoped change to unlock it — not an architecture
  rewrite. The fear that "agnosticism + P8 leaves no home for an orchestrator" is
  retired.
- **Positive:** keeps marketing honest — until this ships, "multi-model / multi-
  adapter orchestration" is **Planned**, not a current feature (see the maturity
  matrix, audit group G).
- **Negative / cost:** relaxing the one-adapter-per-session invariant adds
  failure modes (a downstream adapter offline/incompatible mid-chain, presence
  spanning two runtimes, partial-failure recovery across adapters). These must be
  designed before enabling, not after.
- **Deferred:** no code lands from this ADR. Implementation is gated on (a) the
  Claude-only phase ending and (b) the group-B outcome-signal fix landing, so the
  router has real signal. Linked from `strategic-audit-2026-06`.

## See also

- `src/core/thinking_os/dispatcher.py` — the `get_dispatcher()` invariant (the one thing to relax) and the importlib per-agent loader (why P8 is safe).
- [docs/engineering/dispatcher-contract.md](../../engineering/dispatcher-contract.md) — "adapter hint, not switch" and the named follow-up seam.
- [src/core/rules/model-routing.md](../../../src/core/rules/model-routing.md) — the intra-adapter model layer this ADR is distinct from.
