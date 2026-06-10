<!-- domain:INFRA | layer:adr | ssot:true | updated:2026-06-05 -->
---
title: "ADR: Role dispatch stays opt-in; role chain is single-agent guidance"
domain: INFRA
layer: adr
status: accepted
updated: 2026-06-05
---

# ADR: Role dispatch stays opt-in; the role chain is single-agent guidance

## Status

Accepted (2026-06-05). Supersedes the "Phase 9" deferral framing in
[audit-roles-dead.md](../_meta/audits/audit-roles-dead.md) by making the
decision explicit rather than open.

## Context

The 11-semantic-role system has two layers:

1. **Composition + advancement (always-on, cheap).** On a COMPLICATED/COMPLEX
   gate, `auto-compose-roles.sh` runs the in-process composer and stamps
   `.roles`/`.role`; `advance-role.sh` advances the active role by work phase.
   These feed the banner `roles=` field. **No second agent is spawned.** This is
   advisory cognitive guidance for the one interactive agent.
2. **Real sub-agent dispatch (opt-in, near-dead).** `cos_dispatch_formula_run`
   genuinely spawns a headless Claude sub-session per role with its own prompt,
   schema, and budget; `cos_dispatch_parallel_run` runs several concurrently.
   Live DB evidence: across repo history a real role sub-agent has been
   dispatched ~once; the tool's own docstring steers agents to inline execution
   ("same accuracy, far fewer tokens, no context rebuild penalty").

The product narrative sometimes reads as if the chain "orchestrates" parallel
agents. In practice the default and correct behaviour is single-agent role-phase
guidance.

## Decision

1. **Keep dispatch opt-in. Do NOT auto-fire it.** Building auto-dispatch
   (audit-roles-dead fixes #2/#3) for a path with no caller is speculative
   distributed-systems machinery — a Rule 22 (anti-over-engineering) violation.
   The cheap inline path is the right default for single-user sequential coding.
2. **Label honestly.** The role chain is "single-agent role-phase guidance
   surfaced in the banner," not parallel orchestration. Docs that imply
   otherwise should link here.
3. **Fix the plumbing, not the architecture.** The one exercised dispatch path
   (the completion-guardian `exhaustive_evidence` record) was failing silently;
   `formula_dispatches.error` (migration v34, B5) now captures the reason so the
   failures are diagnosable. That is the right-sized fix.

## When to revisit (build real dispatch)

Build real parallel dispatch only when there is a concrete caller whose value is
**independence/parallelism**, not sequence. The clearest candidate: an
**independent reviewer sub-agent** for `audit_exhaustive` tasks, where a second
context with no generator history catches more than self-review. Before shipping
it, the prerequisites are: a per-chain (not just per-role) budget ceiling, and
EvidenceBundle write-locking (the single-file-per-session bundle is not
concurrency-safe under `cos_dispatch_parallel_run`).

## Consequences

- The role banner remains accurate as *guidance*; readers must not infer that a
  visible `roles=reviewer 2/3` means a reviewer sub-agent ran.
- Consumer projects compose the chain from the meta-repo's generic 11 roles via
  the symlinked hooks. The roles are stack-agnostic, so this is acceptable; a
  dangling meta-repo symlink degrades the chain to blank (same failure class as
  every symlinked hook — `cos sync-doctor --repair`).
- The dormant dispatch infrastructure costs ~0 at runtime and is retained as the
  correct substrate for the future independent-reviewer case.

## References

- [audit-roles-dead.md](../_meta/audits/audit-roles-dead.md) — original diagnosis.
- [agent-economy-and-identity-roadmap.md](../engineering/agent-economy-and-identity-roadmap.md) — S1.
- [src/core/thinking_os/roles/README.md](../../src/core/thinking_os/roles/README.md).
