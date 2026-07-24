<!-- domain:META | layer:adr | ssot:true | updated:2026-07-23 -->
---
title: "ADR-0016: Gated skill-evolution — extend the existing learning loop, do not build a training stack"
domain: META
layer: adr
status: accepted
updated: 2026-07-23
---

# ADR-0016: Gated skill-evolution — extend the existing learning loop, do not build a training stack

Purpose: Record how coding-os should (and should not) adopt the "skill-document-as-trainable-weights" idea from an external, published skill-optimization method — so a future agent extends the existing subsystems instead of standing up a parallel training stack.
Read when: proposing anything that auto-improves skills/rules from experience, or evaluating a "let's train our skills" idea.
Skip when: hand-authoring a single skill or rule.
Read next: [raptor-consolidation.md](../raptor-consolidation.md) · [anti-overengineering.md](../../../src/core/rules/anti-overengineering.md) · [memory.md](../../../src/core/rules/memory.md).

> Nav: [ADR Index](00-index.md) | [Docs Index](../../00-index.md)

## Status

Accepted (2026-07-23).

## Context

An external, published method (2026) treats an agent's natural-language **skill document as the trainable "weights" of a frozen model** and optimizes it with a deep-learning-style loop — rollout (run scored tasks) → reflect (an optimizer model emits bounded add/delete/replace edit patches, the "gradient") → aggregate → select/clip (keep at most `learning_rate` edits) → update → **gate on a held-out validation split (accept only a strict improvement)** — plus a nightly offline companion that harvests real session transcripts, mines recurring tasks, replays them, consolidates behind the gate, and **stages a proposal for a human to adopt**. The deployed artifact is a compact skill doc run against the unchanged model, so it adds **zero inference-time cost**.

A subsystem-by-subsystem audit of coding-os found the fit is real but **narrow**: cos has already, independently, built most of the machinery, and stops one step short of the method's one load-bearing property.

| Method component | Existing cos home |
|---|---|
| Confidence/SGD-step/gradient-clip + weight store | `learned_patterns` + LTP/LTD (`boost_success`/`penalize_failure`) + Ebbinghaus decay ([learning.py](../../../src/core/thinking_os/tools/learning.py), [decay.py](../../../src/core/thinking_os/decay.py)) |
| Nightly offline "sleep" cycle | [nightly.py](../../../src/core/scheduled/nightly.py) CRON A (gated legs) + `responsive_extract` (Stop hook) + CRON B weekly narrative |
| Replay / rollout engine | `sdk_dispatcher.dispatch` — a fresh sub-session against an `agent_file` + `input_slice` |
| Optimizer-model role | the CRON B distiller agent + `cos_learn_narrative` |
| Stage-proposal → human-adopt | `generalize_lessons` → `.coding-os/memory/drafts/`, `cos_promote`, governance task-marker + `block-protected-files.sh` |
| Rejected-edit buffer | decay archive-at-floor (`promoted_to='archived'`) + LTD |

**What cos lacks — and it is the hard piece:** (1) **no held-out validation split exists anywhere** — every gate (verify ledger, DoD, anti-ambiguity) runs the project's own in-band suite against the current tree, never a retained task set scoring a *guidance* edit; (2) the consolidation loop **never emits bounded edits to canonical `SKILL.md` / rule `.md` bodies** (it emits new-file drafts and confidence scalars); (3) the reward label (`agent_metrics.outcome`) is **agent-self-reported and gameable**.

## Decision

1. **Extend three existing subsystems; do not build a training stack.** The value of the external method for cos is conceptual (the gate discipline + an independent reward), not its implementation. Reuse `learning.py`, `nightly.py`, and `sdk_dispatcher`.
2. **Sequence smallest-first, defer the L-effort behind a feasibility spike:**
   - **[TASK-850]** (S, ship-alone value) — derive an additive `derived_outcome` reward label from the tree-keyed verify ledger, not self-report.
   - **[TASK-851]** (spike) — before any eval build, measure whether the real task stream has enough recurring, checkable instances to form a held-out set with signal above stochastic-rollout variance, under a per-night cost ceiling. Go/no-go gates the L-effort.
   - **[TASK-852]** (feature, depends on TASK-851) — only then, bounded `learning_rate`-clipped prose-only edit patches on `SKILL.md`/rule `.md`, staged as drafts and applied only behind the gate **and** a human governance task, with a draft-expiry policy.
3. **Immediate hardening (done in [TASK-849]):** `block-protected-files.sh` now guards the `src/core/skills/` and `src/core/rules/` **sources**, not just their rendered `.claude/` copies — the source propagates to every consumer via live symlinks, so it must carry at least the same governance-marker guard. This is the precondition that makes any future automated skill-editing (TASK-852) *staged and adopted* rather than silently live.
4. **An automated skill/rule editor targets** `SKILL.md` prose bodies + the 8 hand-written rule `.md` + `stack.yaml` source rows — **never** the derived `skill-enforcement.md`/`dimension-registry.md` (regenerated, freshness-gated) and never front-matter (`globs`/`description` are load-bearing for enforcement and trigger accuracy).

### Deliberately not built (parasitic parts avoided)

A new belief/confidence engine · a new scheduler/cron · a new replay engine · a freeform `record(insight)` tool or a from-scratch optimizer agent · a standalone rejected-edit table · a branch/worktree A-B canary (Rule 23 forbids branches) · an optimizer editing the derived rule files. Each already has a home above; adding it would duplicate the `learning.py` loop.

## Raptor-lens review

Per [raptor-consolidation.md](../raptor-consolidation.md) — a design that adds parts must name the capability that pays for each one.

- **Component consolidation (1) + parasitic-complexity elimination (3):** the roadmap adds **zero new subsystems** — every step is a leg, a column, or a patch inside an existing unit. The "deliberately not built" list is the parasitic mass this ADR refuses.
- **Zero-overhead abstraction (2):** the immediate hardening adds **two path checks to one existing hook** and reuses its escape-hatch verbatim — denser coverage, no new mechanism. It is a no-op in consumer projects (they have no `src/core/` tree), so blast radius is meta-repo-scoped despite the live-symlink reach.
- **High cohesion (4):** the reward label lives where the outcome is recorded; the eval leg lives in `nightly.py` beside the mining it depends on; the edit-patch path lives in the distiller that already drafts.
- **Part-count honesty:** the one genuinely new capability — a held-out validation gate — is explicitly gated behind a feasibility spike (TASK-851) because at solo-repo scale its signal-vs-noise is unproven; we do not pay for a part whose capability we have not measured.

## Consequences

- The strongest, lowest-regret move (TASK-850) improves the current loop immediately and stands even if the held-out gate proves infeasible.
- **Biggest risk (recorded, not solved):** a held-out gate may be statistically infeasible on a single-dev repo whose task stream is a long tail of one-offs; stochastic rollouts scoring a thin set decide on sampling noise while spending real per-night cost. TASK-851 exists to kill the build early if so. Without a working gate, auto-editing `SKILL.md` through live symlinks is *more* dangerous than the hand-authored status quo.
- **Reward-hacking:** the ledger label must be paired with a lagging quality signal (rework/reopen rate over following sessions) so an edit that narrows verify scope cannot be accepted as "improvement" (TASK-850/TASK-852 scope note).
- **Human throughput is the real rate limiter:** staged drafts need a human governance task each; without a draft-expiry policy they pile up stale (the icebox-parking failure mode) — TASK-852 owns the decay policy.

## References

- [raptor-consolidation.md](../raptor-consolidation.md) — the architecture-shape lens this design was reviewed against.
- [anti-overengineering.md](../../../src/core/rules/anti-overengineering.md) — reuse-first / no-speculation / defer-by-default.
- [memory.md](../../../src/core/rules/memory.md) — the four-layer model; the existing learning loop this roadmap extends.
- [src/core/hooks/block-protected-files.sh](../../../src/core/hooks/block-protected-files.sh) — the guardrail hardened by TASK-849.
- TASK-849 (this hardening) · TASK-850 · TASK-851 · TASK-852 (the sequenced roadmap).
