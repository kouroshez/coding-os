---
id: TASK-575
title: "Cluster 2 \u2014 Un-inert consumers + data-driven scope: populate enforce_context_on, delete the *core/*.py hardcode + _in_meta_source_tree, render scope from stack.yaml"
swimlane: core
kind: refactor
epic: graph-first-enforcement
labels: [consumer, scope, rule-11, templates, graph-gate, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
depends_on: [TASK-573]
blocked_by: []
references: []
---

# TASK-575: Cluster 2 — Un-inert consumers + data-driven scope: populate enforce_context_on, delete the *core/*.py hardcode + _in_meta_source_tree, render scope from stack.yaml

**Outcome (one sentence):** Consumer projects stop being inert: stack overlays populate graph.enforce_context_on (or it derives from the centrality cache); a stack-agnostic graph-first rule ships into _base so consumers get the always-loaded guidance; graph-explorer is mapped as a consumer-stack secondary. The hardcoded *core/*.py|*cli/*.py|*adapters/*.py literal + _in_meta_source_tree + _graph_module_disabled are deleted from enforce-skill.sh (Rule 11) and the requirement is rendered from the stack.yaml SSOT. Closes B1, B2, B3, B4, B5, D3.

## Read First
- src/core/hooks/enforce-skill.sh
- src/templates/_base/scaffold/.coding-os/rag-config.yaml
- src/templates/meta/stack.yaml
- src/core/rules/skill-enforcement.md
- src/templates/nextjs/stack.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
GIVEN a generated nextjs/fastapi consumer WHEN the agent edits a load-bearing app file THEN enforce_context_on matches and the graph-gate fires (not a silent no-op); GIVEN enforce-skill.sh THEN it contains no stack/path literal (grep clean, Rule 11); AND consumer .claude/rules ships a graph-first rule; AND golden fixtures regen green; AND adapters + template_scaffold matrix suites green.

## Work Log
