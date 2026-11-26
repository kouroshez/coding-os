---
name: plan-from-the-graph-scope-to-the-symptom
description: "Map every consumer of what you change with cos_graph_* before planning, fix only where the bug shows, and run the matrix once at close."
metadata:
  type: feedback
---

Before writing a plan, run `cos_graph_references` / `cos_graph_impact` on every symbol and file layout the change touches and list each consumer in the plan. Fix the bug where it shows, not everywhere a similar shape exists. Run the Verification Matrix once at close, not after each fix.

**Why:** A layout change planned from a partial grep met its six dependents one at a time through failing tests and two critical review findings, three review rounds per task, and hours of repeated suite runs (TASK-1134, 2026-11-26). The bug itself only showed in coding-os, not in consumers.

**How to apply:** For a change to a file layout or shared helper, the plan names its consumers from the graph and the surface where the bug actually shows; anything beyond that is a separate card. Use targeted tests during the work, and run each matrix row once at the end with its exact command (no pipes, no background, no extra flags, or the ledger ignores it). Keep one task per working tree at a time. See [[run-the-feature-not-just-its-tests]] and [[verify-ledger-needs-standalone-runs]].
