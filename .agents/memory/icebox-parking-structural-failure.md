---
name: icebox-parking-structural-failure
description: "Deep-research finding: agents parking tasks in icebox and abandoning them is by-design, not a bug — creation is frictionless/ungated/GC-immune while no autonomous mechanism ever pulls icebox→in_progress. Keystone fix = stamp created_by_session on every card."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2c2873ee-e381-4ed3-8e7a-f733bf41ed74
---

Operator's standing complaint (2026-07-17): agents create tasks, leave them parked in `icebox` as defer/not-now/future/backlog, and under autonomous (no-human) operation nothing picks them back up, so the backlog rots and development stalls.

**Diagnosis (10-agent adversarially-verified deep research):** this is the emergent, fully-compliant behavior of the system *as designed*, not a bug. Root causes, ranked:

1. **Creation/completion asymmetry, zero exit-pressure.** Parking is the frictionless default (`status=icebox, ready=False, agent_session=NULL`); starting work is effortful (ready+deps+DoR+WIP gates); `icebox` has 3 exits (`workflow.py:47`) and none is ever timed/forced toward work. `icebox_auto_archive_days=0` (off; `config.py:193`), stale-flag is cosmetic-only.
2. **No autonomous drain loop.** `cos_task_claim_next` is single-shot/voluntary; its only real caller is `cos pr open` (pr-mode, default-OFF, coding-os stays trunk). `nightly.py` never pulls and is a net *producer* of icebox tasks.
3. **Pull filter needs a label create-default never sets** — `cos_task_pick` requires `labels LIKE '%"ready"%'`; create-default cards are invisible forever (reclaim/cascade/nightly cards ARE re-readied, so scope the blame to create-default).
4. **Enforcement blind spot** — `warn-abandoned-task` + `session-end` + reclaim + `cos_task_reconcile` all filter on `in_progress`/`testing`+`agent_session`; a create-then-park card matches nothing at every event. DB has no session-ownership column on icebox cards.
5. **Observability blind spot** — no metric for backlog size / abandonment; the 4 outcomes have no "abandoned"; the learning loop can never learn "this agent parks tasks."
6. **Module disable makes it worse-or-same** — the `tasks` module (`subsystems.yaml:109`, kernel:false) owns every abandonment detector; disabling it removes them while raw-file parking (`status: icebox`) still works with zero detection.

**Governance contradiction (the real hole):** Rule 22 "Defer-by-Default / file a task" is permanent constitutional law; the only counter-norm is the decayable memory [[no-parking-actionable-findings]] whose boundary is self-admittedly "still undefined."

**Recommended fix path (NOT yet implemented, no tasks created — dogfooding the anti-park discipline):** keystone = **QW-3: stamp `created_by_session` on every card at creation** (append-only migration vN+1) — unblocks a create-then-park detector hook (DC-3), a create-then-park warning (QW-2), and a backlog-health metric (DC-5). Highest-leverage but governance-shifting: **DC-1** an opt-in autonomous backlog-drain loop; **DC-2** promote the anti-park norm into a real `tasks`-module rule with an enforceable "fix-now vs file-a-card" boundary.

**Full report artifact:** https://claude.ai/code/artifact/1e8cf6a1-5e81-44db-97c0-5f81f2289238

**Why:** the operator wants autonomous agents that don't stall; this failure is the single biggest blocker to unattended operation. **How to apply:** when asked to fix it, open ONE task and take QW-3 to done in-session; do not spawn a pile of recommendation cards (that would re-enact the exact failure). See also [[no-parking-actionable-findings]].
