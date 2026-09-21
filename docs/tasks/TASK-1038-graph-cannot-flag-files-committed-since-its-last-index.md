---
id: TASK-1038
title: "Graph cannot flag files committed since its last index"
swimlane: infra
kind: feature
epic: null
labels: [ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-09-15
started: 2026-09-20
completed: null
agent_session: ses-claude-20260920-211122-bc06
depends_on: []
blocked_by: []
references: []
---
# TASK-1038: Graph cannot flag files committed since its last index

**Outcome (one sentence):** An agent can ask which indexed files have changed in git since the graph last read them, so a confidently complete answer built on a stale index is detectable before it is acted on.

## Read First
- src/core/graph_os/tools/_analysis_impact.py
- src/core/graph_os/backends/_sqlite_read.py

Extraction short-circuits on a per-file content_hash, so an edited file is
re-read on the next index pass. What has no detector is the window between a
commit and that pass: the graph is complete against its own model and the model
is behind the tree, and nothing in the envelope is truncated, so no flag is
raised.

Raised on r/LLMDevs (2026-09-14): the truncation flag works because the harness
knows it truncated. Staleness has no equivalent because the system believes it is
fine. The cheap external check named there is comparing indexed files against
files with commits after the last index timestamp, which turns "possibly stale"
into a list without needing a second analyzer.

The expensive version, comparing graph edges against the code, is deliberately
out of scope: it needs an analyzer that does not share the extractor's blind
spots, and two runs of the same extractor agree everywhere it is wrong.


## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** files committed after the graph's last index pass
  **When** the staleness query runs
  **Then** it returns those paths and the age of the index, and an empty list when the index is current.
- **Given** a repo with no git history available
  **When** the query runs
  **Then** it reports that it cannot answer rather than returning an empty list.

## Work Log
- 2026-09-21 [claude]: Edit patch_stale_doc.py
- 2026-09-21 [claude]: Edit patch_stale_tool.py
- 2026-09-21 [claude]: Edit patch_stale_mcp.py
- 2026-09-21 [claude]: Built cos_graph_stale_files: reads file_index_state for indexed paths and their last_indexed_at, asks git which of…
- 2026-09-21 [claude]: Edit patch_bench_doc.py
