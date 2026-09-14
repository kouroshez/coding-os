---
name: check-the-card-premise-before-fixing-it
description: "An icebox card's stated root cause is a hypothesis from the day it was filed; re-measure before building the fix it asks for."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-14T02:34:31.840Z
---

Every icebox card older than a few weeks describes the world as it was on the day someone filed it. Three of eight cards drained on 2026-09-13 had premises that no longer held, or never held:

- **TASK-1002** blamed "long-lived MCP readers pin a read snapshot". Probed it: an idle pooled reader does *not* block checkpointing (`busy=0`, WAL truncated to 0); an **unfetched cursor** does (`busy=1`, 114 pages pinned). Two of its three acceptances had already been met by a later task.
- **TASK-1004** asked to split three files the project had *itself recorded as exceptions* six days earlier in `ci-gates.md`. The real defect was two gates reading two exemption lists.
- **TASK-996** was a zombie with completion evidence, but re-running its preflight showed 3 of 4 prerequisites still missing — genuinely blocked on a credential only the operator can supply.

**Why:** building the fix a stale card describes wastes the work and can make things worse — splitting an append-only migration ledger to satisfy a number would have created a permanent "which file does v55 go in?" question.

**How to apply:** before starting any card you did not file this session, run the thing it claims. `df`, the preflight, the query, the probe. Then say plainly in the work log what you measured and how it differs from the card. If the premise is dead, close or re-scope the card with the measurement rather than implementing against it. Related: [[dry-run-in-repo-before-trusting-units]], [[icebox-parking-structural-failure]].
