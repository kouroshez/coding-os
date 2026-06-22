---
id: TASK-020
title: "doctor panel: replace raw JSON with structured issue cards"
swimlane: core
kind: feature
epic: null
labels: [doctor, ui, observability]
status: archive
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/web/ui/src/pages/DoctorPage.tsx
  - src/core/graph_os/tools/graph.py
---
# TASK-020: doctor panel — replace raw JSON with structured issue cards

**Outcome (one sentence):** The Diagnostics → Doctor → Backend tab no longer dumps the `issues` array as raw JSON; each category renders as a titled card with a count badge and a sortable sample table.

## Read First
- [src/core/web/ui/src/pages/DoctorPage.tsx](../../src/core/web/ui/src/pages/DoctorPage.tsx) — `BackendTab()` (lines 113-149) — the `<pre>{JSON.stringify(...)}</pre>` to replace
- [src/core/graph_os/tools/graph.py](../../src/core/graph_os/tools/graph.py) — `cos_graph_doctor()` (lines 2250-2447) — issue shape contract

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Doctor backend tab opens with N graph issues
- **When** the user inspects the page
- **Then** each issue category is its own card showing title + count badge + top-5 sample rows in a table (no raw JSON `<pre>`); flat stats render in the existing top grid; build clean.

## Work Log
- 2026-05-23 — rewrote `BackendTab()` in DoctorPage.tsx: typed `GraphDoctorData` interface, new `IssueCard` component (label + count badge + sortable sample table with derived columns), top stat tiles (Health / Nodes / Edges / Issues) replace the JSON dump. `Section.title` widened to `React.ReactNode` so the count badge can render inline. `npm run build` clean (1.79s, no TS errors).
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
