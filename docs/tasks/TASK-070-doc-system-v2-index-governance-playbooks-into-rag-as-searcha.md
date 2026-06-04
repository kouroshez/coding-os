---
id: TASK-070
title: "doc-system-v2: index governance + playbooks into RAG as searchable low-priority source-types (cross-ref discovery)"
swimlane: thinking_os
kind: feature
epic: doc-system-v2
labels: [rag, retrieval, doc-system]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-04
started: 2026-06-03
completed: 2026-06-03
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-070: doc-system-v2: index governance + playbooks into RAG as searchable low-priority source-types (cross-ref discovery)

**Outcome (one sentence):** cos_doc_search surfaces always-active rules + routing playbooks (new low-priority source-types) so an agent discovers a related rule even with no explicit link — closing failure F1 — without changing their always-active/skill loading.

## Read First
- docs/engineering/doc-system-overhaul-roadmap.md
- .coding-os/rag-config.yaml
- src/core/thinking_os/tools/docs.py
- src/core/graph_os/extractors/md_links.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** governance rules + routing playbooks are in the `exclude` list of `rag-config.yaml` so `cos_doc_search` cannot surface them (gap G1, failure F1).
- **When** they are registered as RAG `sources` with distinct low-priority source-types (`governance`, `playbook`; priority ≤0.4) — removed from `exclude` — in the template SSOT (`src/templates/_base/scaffold/.coding-os/rag-config.yaml` + sibling stack copies) and the meta-repo live config, then the index is rebuilt (`cos docs-index --force`).
- **Then** `cos_doc_search("trunk-based git")` and `cos_doc_search("docs-first")` return the governance chunk; higher-priority engineering docs still outrank governance for actionable queries; always-active rule loading and playbook-as-skill loading are unchanged; `uv run --extra rag pytest src/core/thinking_os/tests/ -q` is green.

## Work Log
- 2026-06-04 [claude]: Status transitioned to complete via cos task-done.
- claude: governance(0.6,−_templates/archive)+playbooks(0.5) moved rag exclude→sources in _base+react-native+live; reindex 689 chunks errors=0.
- claude: cos_doc_search now surfaces governance(docs-first/Rule23)+playbook(security-review); eng still outranks impl queries. 116 doc + 44 scaffold/golden + docs-lint green.
