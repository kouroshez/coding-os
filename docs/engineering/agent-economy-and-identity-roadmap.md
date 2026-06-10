<!-- domain:INFRA | layer:spec | ssot:true | updated:2026-06-05 -->
---
title: Agent Token-Economy & Identity Roadmap
domain: INFRA
layer: spec
status: active
updated: 2026-06-05
---

# Agent Token-Economy & Identity Roadmap

SSOT for the agent-behaviour initiative: how the coding-os agent governs
token use across its output surfaces, what it injects into the chat, and the
identity/persona it imposes. Grounded in a 6-dimension reverse-engineering +
adversarial-critique pass (transcript on file). This doc is the doc-anchor for
the code changes it specifies.

## The reframe (central finding)

The instinct "we removed RTK/caveman, we need a token compressor" is
half-mis-targeted:

- **RTK** ("Rust Token Killer") was an *external* lossy Bash-output compressor
  (60-90%). It conflicts with this system because correctness depends on
  **exact symbol/row fidelity** — graph rename/blast-radius, the search skill's
  ground-truth counting, and doctor's DB audits all act on literal output.
  Lossy compression there is not "fewer tokens", it is "wrong answer, silently"
  (`compose_chain` rendered as `n`). RTK operated on **input** context, never
  the chat reply.
- **"caveman"** was never compression — it is an *always-on visibility* pattern
  (the inspiration for `USER_BANNER` + session recap), the opposite of token
  reduction.

Therefore the replacement is **not** a generic compressor. It is two things:

1. **Input economy** is already strong and lossless (graph-first envelopes,
   deferred tool schemas, model tiering, the 32 KB reactive budget, structured
   `@safe_tool` envelopes) — this is Anthropic's own structural menu. Keep it.
2. **Output economy** — the agent's **chat reply to the user** — is the real
   ungoverned gap, and the correct fix is a persona-level conciseness directive,
   not a hook (a Stop hook fires *after* generation; it cannot save the turn's
   tokens and adds per-turn input cost).

## Output token-economy scorecard

| Output surface | Governance | Enforcement | State |
|---|---|---|---|
| Commit messages | Rule 24 | Hook BLOCK (2 layers) | strong |
| Code comments | Rule 12 | convention | good (index drift — B6) |
| Code volume | Rule 22 + clean-code | convention + skill | good |
| **Chat reply to user** | **none** | **none** | **the gap (A1)** |

Output tokens cost ~4-5x input. The chat reply is the highest-frequency,
highest-variance output surface and is the single largest controllable
output-token line item per session.

## What is injected into the chat (banner/pulse inventory)

Per-turn (`UserPromptSubmit`): `[coding-os pulse]` (agent-only, inside a
hidden `system-reminder`) + `USER_BANNER` (echoed by the agent as line 1).
Per-session (`SessionStart`): primer cards + digest + tasks + uncommitted +
MCP-prime. Per-turn (`Stop`): counts-only recap.

Two critical corrections that resize the "context tax":

1. **Adapter-scoped.** On Codex the `UserPromptSubmit` dispatcher discards
   stdout, so the per-turn injection tax is ~0 and the banner does not render;
   Codex.app fires 0/75 hooks. The tax is a Claude (and partially Cursor)
   phenomenon.
2. **Prompt-cached.** The standing context (CLAUDE.md + rules) is a cache read
   (~90% discount), so the steady-state marginal cost is the ~120-token dynamic
   pulse/banner, not the raw 6-12k.

The literal banner field names (`gate=COMPLICATED 4`) are **load-bearing** —
they map 1:1 to the state files the user overrides; translating them breaks
traceability (an explicit anti-pattern in `transparency-banner.md`). The
enterprise improvement is progressive disclosure + a narrative recap (U1), not
a unified renderer (the six surfaces map to six harness-owned channel
lifetimes and cannot be merged).

## Correctness defects (bugs that make the system lie)

| # | Defect | Why it matters | Fix |
|---|---|---|---|
| B1 | `chars/4` token estimate undercounts non-Latin (CJK/Arabic/Cyrillic) ~2-3x | `meta.truncated` (the graph-first coverage signal) silently lies on non-English payloads → agent acts on incomplete data | script-aware conservative estimate in `_shared.py` + `estimate_tokens.py` |
| B2 | `compress.py` lossily LLM-rewrites ground-truth memory rows, no symbol guard | the RTK failure mode relocated to the memory layer; a future session trusts a model-invented fact | preserve identifiers/symbols + honest labeling + opt-in guard |
| B3 | Codex `advance-role` never fires on Write/Edit | banner shows a frozen/wrong role through implementation | **DEFERRED — Codex-only; verified correct on Claude (Write/Edit PostToolUse fires). Out of scope this Claude-only phase.** |
| B4 | `classify-task-mode` ordering | banner mode could lag a turn on Codex | **DEFERRED — Codex-only; verified correct on Claude (order is …→classify-task-mode→session-context). Out of scope this phase.** |
| B5 | `formula_dispatches` has no error column; the one live dispatch path fails ~42% silently | the only exercised multi-agent path is undiagnosable | append-only migration v34 adds an `error` column; both write sites populate it on non-ok status |
| B6 | Rule 12 index cites a non-existent `lint-function-header.sh` | reader believes comment bloat is hook-enforced | delete the stale citation |
| B7 | Fresh-panel turn-1 banner renders all-blank (`ses=?`) | looks like a hung agent — worst first impression | graceful placeholder when session-id not yet seeded |

## Decisions (what we build vs reject)

Build (surgical, evidence-ranked): B1-B7, A0 (measure first), A1 (one
mode-keyed reply rule), U1 (template recap), S1 (honest labeling + dogfood +
deferred-dispatch ADR).

Reject as over-engineering (Rule 22): Stop-hook reply-length nudge (fires after
generation), context-broker / budget-eviction subsystem (cached, ~120-tok
floor), unified banner renderer (harness owns the channels), Message Batches
wiring (most "overnight" jobs call no LLM), build-real-parallel-orchestration
(no caller), re-adding any generic compressor (wrong tool for exact-fidelity).

## Phased roadmap

- **Phase 0 — correctness:** B1 → B2 → B5 → B6 → B7. Each a separate commit.
  (B3, B4 are Codex-only and verified correct on Claude — deferred this phase.)
- **Phase 1 — output gap:** A0 measured 7,658 real assistant turns from on-disk
  transcripts: visible-reply median **36 tok**, p90 **128**, only **2-4%** exceed
  300 tok (and those are the deliberate reports the user wants verbose). Output is
  **already lean** — an enforcement rule is NOT warranted (it would risk truncating
  the 2-4% wanted-verbose turns for no real gain; and a Stop hook fires after the
  reply is already billed). A1 therefore narrows to a **brief codified lean-output
  principle** (lead with the answer, concise by default, expand for deliberate
  reports, push tables/logs to artifacts) folded into the existing reply rule
  (`transparency-banner.md`) — codifying current good behaviour for enterprise
  durability + consumer propagation, with **no hook**.
- **Phase 2 — depth UX:** U1 (narrative, template-based Stop recap).
- **Phase 3 — multi-agent honesty:** S1 plumbing + honest labeling; defer the
  real-dispatch architecture to a documented decision.
- **Phase 4 — enterprise i18n:** scoped as a tracked epic (**TASK-188**) — ~24
  product files across three classes that must NOT be swept uniformly:
  presentation → English; functional heuristic classifiers → English-default
  (needs a product decision + golden/test regen); and the commit prompt-leak
  guard's non-Latin detection is **KEPT** (it keeps Persian out of git history,
  which serves the goal). Deliberately not rushed at session-tail — that would be
  the "quick hack now" anti-pattern the owner forbade.

## Cross-cutting constraints

**Scope this phase: Claude adapter only** (per product owner) — Codex/Cursor
parity items are deferred and explicitly marked. Single-agent writes (Rule 21 +
gate machinery); agent team only for read-only review. Trunk-based, explicit-path
commits, commit-message contract. English, enterprise-grade in every authored
artifact. Anti-over-engineering on every item.
