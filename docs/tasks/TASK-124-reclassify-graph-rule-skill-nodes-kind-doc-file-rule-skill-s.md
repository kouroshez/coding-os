---
id: TASK-124
title: "Reclassify graph rule/skill nodes (kind=doc_file\u2192rule/skill) + surface missing-frontmatter chunk count"
swimlane: "graph_os"
kind: bug
epic: doc-system
labels: [docs-system, graph, rag, audit-d3-f5, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-124: Reclassify graph rule/skill nodes (kind=doc_file→rule/skill) + surface missing-frontmatter chunk count

**Outcome (one sentence):** Rule/skill nodes classify to their governance kind (not doc_file) deterministically across re-index — verified already-correct in the live graph (git-workflow=rule, clean-code=skill via cos_graph_query, so no migration is needed) and guarded by a determinism test; and the doc indexer surfaces the count of indexed files with a body but no parseable frontmatter (was a silent logger.debug) so Stage-1 metadata gaps are visible in the index summary.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/graph_os/extractors/md_links.py
- src/core/thinking_os/doc_indexer.py

## Repro Steps
1. Index a docs tree containing a file with a body but no `<!-- domain:... -->` header.
2. Inspect the index `stats` dict — there is no count of files missing frontmatter; the gap is only a silent logger.debug, invisible in the summary.
Expected: stats reports `missing_frontmatter`, and rule/skill paths classify to a non-doc_file governance kind deterministically.
Actual: missing-frontmatter count invisible; classification determinism unguarded by a test.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the doc indexer processes a docs/ tree and the md_links extractor sees governance paths
- **When** `cos graph-reindex` / the indexer runs
- **Then** the index stats include a `missing_frontmatter` count; src/core/rules/*.md and skills/**/SKILL.md classify to a non-doc_file governance kind, stable across repeated extraction (guarded by a test in test_md_links); a plain docs/ file stays doc_file — verified by test-graph_os + test-thinking_os.

## Work Log
- 2026-06-06 [claude]: Reclassification verified ALREADY-correct in the live graph (cos_graph_query: git-workflow=rule, clean-code=skill, conf
- 2026-06-06 [claude]: committed 44778daa: src/core/graph_os/tests/test_md_links.py, src/core/thinking_os/doc_indexer.py, src/core/thinking_os/
