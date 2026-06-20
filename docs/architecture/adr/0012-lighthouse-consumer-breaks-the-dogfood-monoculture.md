<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-20 -->

# ADR-0012: A lighthouse consumer (streamos) breaks the dogfood monoculture

- **Status:** Proposed (2026-06-20, audit group F) — strategy + first lighthouse named; the multi-week build is owner-driven
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** flywheel, dogfood, monoculture, metrics, learning, strategic-audit-2026-06

## Context

The strategic audit (2026-06-19) named **dogfood monoculture** the master risk,
upstream of every other finding. The evidence:

- Essentially all recorded work is **INFRA** (the meta-repo building itself);
  near-zero **FRONTEND**, little **BACKEND**. The cognitive loop has **never run
  on a real consumer application**.
- This makes every "intelligence" claim **unfalsifiable**: the flywheel shows
  98.75% `success` not because the system is brilliant but because one agent does
  one kind of well-understood INFRA work. `cos_route_model` cannot give a
  differential recommendation (one model family, one domain, all CLEAR/COMPLICATED);
  `learn_extract` mints almost nothing (no variance to learn from); the formula
  composer sits dormant (interactive INFRA rarely triggers COMPLICATED+ dispatch).

The other remediations close the *mechanism* gaps but not the *signal* gap:

- **B1 (TASK-463)** wired a real `blocked` outcome emit path, so non-`success`
  outcomes are now structurally *possible*.
- **B5/C1/D/G/461** removed dead weight, cut the token floor, and made coverage
  honest.

But wiring an emit path does not create variance — only **diverse real work
does**. A flywheel that only ever turns on INFRA tasks stays degenerate no matter
how clean its plumbing. The missing input is a real, non-INFRA application driving
genuine FRONTEND/BACKEND tasks — with their reworks, blocks, and partial outcomes —
through the same board, metrics, and learning loop.

## Decision

**Adopt `streamos` as the first lighthouse consumer. The monoculture is broken by
running the full cognitive loop on a real app, not by more meta-repo work. The
multi-week build is owner-driven; this ADR fixes the strategy, the choice, and the
success criteria so the work is measured, not vibes.**

1. **Lighthouse = `streamos`** (`/Users/ciro/Files/Project/streamos`, Go +
   SvelteKit). It is already a registered consumer with a live
   `.coding-os/coding-os.db` and a seeded board — "half-wired" exactly as the
   audit found. It is a real product (BACKEND + FRONTEND), not INFRA, so its work
   exercises the dimensions the meta-repo never does.
2. **What "running the loop" means** — real streamos feature/bug work flows
   through `cos task-*` (BACKEND + FRONTEND swimlanes), classified through the
   Cynefin gate, executed with the stack skills, verified, and **closed with
   honest outcomes** (the B1 `blocked` path + explicit `partial` when acceptance
   is only partly met). The point is the outcome *distribution*, not task count.
3. **Success criteria (the falsifiability test)** — the lighthouse is working when,
   on streamos's own DB: (a) `task_outcomes` carries a **non-degenerate** mix
   (success / rework / blocked, not ~99% success); (b) ≥1 domain other than INFRA
   has enough samples for `cos_route_model` / `learn_suggest` to return a
   history-backed, *differential* recommendation; (c) `learn_extract` promotes at
   least one pattern from real non-INFRA work. Until then, "the system makes agents
   smarter" remains unproven.
4. **This is the demand-driver for depth-over-breadth (report §S4).** Stack work
   is justified by a real consumer needing it (streamos's Go + SvelteKit stacks
   earn promotion to *stable* via [stack-maturity.md](../../governance/stack-maturity.md)),
   not by minting stack #27.

## Consequences

- **Positive:** the headline differentiator ("a cognitive OS that makes agents
  measurably better over time") gets its first **falsifiable** test bed. The
  flywheel finally has variance to learn from; the B1 emit path has real signal to
  carry.
- **Positive:** streamos doubles as the proof that the consumer-distribution seam
  (ADR-0010) and cross-adapter seam (ADR-0011) are needed *before* a second
  external consumer — the lighthouse surfaces those pressures first.
- **Negative / cost:** this is **weeks of real product work**, owner-driven, not a
  meta-repo refactor an agent finishes in a session. It also splits attention
  between building coding-os and building streamos — that tension is the point
  (dogfood), but it is real.
- **Deferred:** no code lands in the meta-repo from this ADR. It is the strategic
  decision + measurable success criteria. Progress is tracked on **streamos's own
  board**, not here. Linked from memory `strategic-audit-2026-06`.

## See also

- [docs/governance/stack-maturity.md](../../governance/stack-maturity.md) — the depth-over-breadth promotion path streamos drives.
- [docs/engineering/learning-extraction.md](../../engineering/learning-extraction.md) — the variance-gated learning the lighthouse feeds (B1 emit path).
- [ADR-0010](0010-consumer-distribution-version-gate.md) · [ADR-0011](0011-cross-adapter-orchestration-seam.md) — seams the first real consumer makes urgent.
- Memory `strategic-audit-2026-06` — the audit that named monoculture the master risk.
