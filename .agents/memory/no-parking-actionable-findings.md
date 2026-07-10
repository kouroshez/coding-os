---
name: no-parking-actionable-findings
description: "User forbids parking small, immediately-fixable findings as icebox tasks — fix them in-session and close the loop; icebox should stay empty."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 22f2ad1d-518d-4327-a1f9-b76b2563de1a
---

When I discover a small, well-understood defect during a session (clear outcome, ≤~2h appetite, evidence already in hand), I must FIX it in the same session — inside the active task or a task I immediately start, move to testing, verify, and complete — not file it as an icebox/ready card and end the turn.

**Why:** The user (2026-07-10) pushed back on parking TASK-807 as a card: if the outcome is already known and the fix is in reach, creating a backlog card is deferral theater. He wants the icebox empty and the work done in-session.

**How to apply:** Task cards are only for (a) genuinely large/blocked work, or (b) bugs the agent is SURE about that conflict with project logic/best practice — and the exact rules for that category are still undefined (deferred while the memory-system discussion is ongoing). Default: do it now, task-cycle it (create→start→fix→testing→done) in one pass, push, report. Never leave a card I created sitting in icebox at turn end.
