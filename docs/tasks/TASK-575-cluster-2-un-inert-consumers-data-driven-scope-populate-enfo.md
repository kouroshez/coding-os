---
id: TASK-575
title: "Cluster 2 \u2014 Un-inert consumers + data-driven scope: populate enforce_context_on, delete the *core/*.py hardcode + _in_meta_source_tree, render scope from stack.yaml"
swimlane: core
kind: refactor
epic: graph-first-enforcement
labels: [consumer, scope, rule-11, templates, graph-gate, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260625-122147-96fb
depends_on: [TASK-573]
blocked_by: []
references: []
---
# TASK-575: Cluster 2 — Un-inert consumers + data-driven scope: populate enforce_context_on, delete the *core/*.py hardcode + _in_meta_source_tree, render scope from stack.yaml

**Outcome (one sentence):** Consumer projects stop being inert: stack overlays populate graph.enforce_context_on; a stack-agnostic graph-first rule ships into _base; the hardcoded *core/*.py|*cli/*.py|*adapters/*.py literal + _in_meta_source_tree + _graph_module_disabled are deleted from enforce-skill.sh (Rule 11), the graph-explorer requirement reads from the per-consumer rag-config enforce_context_on SSOT, and the meta repo's own config keeps the broad globs so its dogfood enforcement is preserved. Closes B1, B2, B3, B4, B5, D3.

## Read First
- src/core/hooks/enforce-skill.sh
- src/templates/_base/scaffold/.coding-os/rag-config.yaml
- src/core/hooks/_helpers/graph_context_match.py
- .coding-os/rag-config.yaml
- src/templates/nextjs/stack.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** the meta repo's own rag-config, **When** an agent edits a src/core load-bearing file without graph-explorer, **Then** the graph-gate still blocks (no backward-compat narrowing vs the old hardcode).

**Given** enforce-skill.sh, **When** grepped, **Then** it carries no stack/path literal and no _in_meta_source_tree (Rule 11) — the requirement reads from rag-config enforce_context_on.

**Given** a generated nextjs/fastapi consumer, **When** the agent edits a load-bearing app file, **Then** enforce_context_on matches and the gate fires (not a silent no-op); **And** the consumer ships a stack-agnostic graph-first rule.

**Then** golden fixtures regen green; **And** the adapters + template_scaffold matrix suites are green.

## Work Log
- 2026-06-25 [claude]: Edit enforce-skill.sh
- 2026-06-25 [claude]: Edit .gitignore
- 2026-06-25 [claude]: Landed: enforce-skill.sh now data-driven — deleted the *core/*.py|*cli/*.py|*adapters/*.py literal +…
- 2026-06-25 [claude]: Edit 0014-unified-graph-gate-enforced-dependency-check-before-edit.md
