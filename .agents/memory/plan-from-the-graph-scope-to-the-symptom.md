---
name: plan-from-the-graph-scope-to-the-symptom
description: "Map every consumer of what you change with cos_graph_* before planning, fix only where the bug shows, and run the matrix once at close."
metadata:
  type: feedback
---

Before writing a plan, run `cos_graph_references` / `cos_graph_impact` on every symbol and file layout the change touches and list each consumer in the plan. Fix the bug where it shows, not everywhere a similar shape exists. Run the Verification Matrix once at close, not after each fix.

**Why:** On 2026-11-26 TASK-1134 (Codex skipped symlinked `SKILL.md` files) only affected coding-os itself, since consumers already held real copies. The plan was written after a partial grep and changed the consumer pipeline too. Six dependents of the per-file skill layout (`_update_manifest`, `_skill_selection`, `link_form`, `remove_stack`, `_localize_links`, `install-adapter.sh`) then surfaced one by one through failing tests and two critical review findings: a user's edit written into the shared source, and a disabled stack skill's source deleted. Three review rounds and about eight 5-minute CLI suite runs followed; two tasks took three hours. The owner called it out: the graph went unused and the plan was made up as the work went.

**How to apply:** For a change to a file layout or shared helper, the plan names its consumers from the graph and the surface where the bug actually shows; anything beyond that is a separate card. Use targeted tests during the work, and run each matrix row once at the end with its exact command (no pipes, no background, no extra flags, or the ledger ignores it). Keep one task per working tree at a time. See [[run-the-feature-not-just-its-tests]] and [[verify-ledger-needs-standalone-runs]].
