---
id: TASK-981
title: "Correct the token-savings claims in README and repo docs"
swimlane: docs
kind: bug
epic: honest-benchmarks
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-15
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-981: Correct the token-savings claims in README and repo docs

**Outcome (one sentence):** Every published savings number is reproducible, is measured against a baseline a competent agent would actually run, and is stated net of the always-on context cost.

## Read First
- README.md
- docs/engineering/third-party-token-bench.md
- docs/engineering/graph-hallucination-cures.md
- docs/engineering/graph-use-cases.md

## Repro Steps
README.md:421 publishes "cos_graph_impact — 508 impacted … 7,962 tok … 98.3%". Running the tool live: at the default visit_limit=500 the envelope carries walk_truncated=true and impacted_count=512; raising visit_limit to 2000 gives the true impacted_count=1,494 and 6,114 tokens. The published row is therefore a truncated answer with a cap-artifact count, compared against a complete manual read.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the README benchmark section, **When** a reader checks any number in it, **Then** it came from a non-truncated envelope and the impacted count is the true one, not a visit_limit artifact.
- **Given** a savings percentage, **When** it is published, **Then** the baseline it is measured against is named, and a competent-agent baseline (grep plus bounded reads) is shown alongside the read-everything one.
- **Given** the savings claim, **When** a reader reaches it, **Then** the always-on context cost appears in the same section, per project profile, so the net is visible and not buried.
- **Given** every remaining "97%"-style claim in docs/engineering, **When** the sweep is done, **Then** each is either re-measured or removed.

## Work Log
