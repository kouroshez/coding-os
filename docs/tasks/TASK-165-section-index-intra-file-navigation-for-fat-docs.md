---
id: TASK-165
title: "Section index — intra-file navigation for fat docs"
swimlane: thinking_os
kind: feature
epic: retrieval-pipeline
labels: [retrieval, hooks, mcp]
status: testing
priority: P1
appetite: "1d"
created: 2026-04-30
started: 2026-04-30
completed: null
agent_session: ses-claude-20260430-160051-735a
depends_on: [TASK-155, TASK-157, TASK-161]
blocked_by: []
references:
  - docs/engineering/section-index.md
---
# TASK-165: Section index — intra-file navigation for fat docs

**Outcome (one sentence):** Auto-maintained `<file>.INDEX.md` sidecars + `cos_doc_section` MCP tool let agents navigate inside fat docs at slug granularity, cutting per-section read cost from full-file (≥5k tokens) to slice-only (≈300–800 tokens).

## Read First
- [docs/engineering/section-index.md](../engineering/section-index.md) — canonical spec
- [scripts/regen_doc_index.py](../../scripts/regen_doc_index.py) — pattern to mirror
- [core/hooks/auto-regen-doc-index.sh](../../core/hooks/auto-regen-doc-index.sh) — hook skeleton
- [core/thinking_os/tools/docs.py](../../core/thinking_os/tools/docs.py) — MCP plug-in point

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a 600-line markdown doc, **When** an agent calls `cos_doc_section(path, slug)`, **Then** response carries only the matching section body (≤1500 tokens) plus meta `{start, end, lines, token_estimate}`.
- **Given** a 350-line doc, **When** edited, **Then** no INDEX sidecar is created.
- **Given** a 600-line doc, **When** edited, **Then** within 6s its `<file>.INDEX.md` reflects the new heading structure.
- **Given** a heading rename inside a fat doc, **When** an agent queries the old slug, **Then** the tool returns `fail("not_found", ...)` and a hint to use `cos_graph_rename_plan`.
- **Given** scripts/regen_section_index.py invoked with `--dry-run`, **When** run on a fat doc, **Then** it prints proposed INDEX without writing.

## Work Log
- 2026-04-30 [claude]: spec doc + task created, anchor set
