---
id: TASK-049
title: "Dependency upgrade sweep — all Python+JS deps to latest incl. runtime majors"
swimlane: infra
kind: chore
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-05-31
started: 2026-05-30
completed: 2026-05-30
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-049: Dependency upgrade sweep — all Python+JS deps to latest incl. runtime majors

**Outcome (one sentence):** Every Python and JS dependency upgraded to its 2026-05 latest — including runtime majors (React 19, Vite 8, react-router 7, claude-agent-sdk 0.2, tree-sitter 0.25, torch/transformers) — with each tier verified green before the next.

## Read First
- pyproject.toml — Python deps + intentional caps (tree-sitter P-I-11, claude-agent-sdk <0.2)
- src/core/web/ui/package.json — hub UI deps
- src/adapters/claude/sdk_dispatcher.py — claude-agent-sdk 0.2 contract surface
- src/core/graph_os/extractors/ — tree-sitter AST consumers (parity after grammar bump)

## Acceptance
- [ ] Safe within-range bumps applied; baseline suites green
- [ ] JS dev-tooling majors (TS6, ESLint10, Vitest4, jsdom) green
- [ ] Vite 8 build+dev green
- [ ] React 19 + ecosystem green (build, typecheck, vitest, playwright a11y)
- [ ] Python heavy (cryptography48, ML stack) green
- [ ] claude-agent-sdk 0.2 dispatcher adapted, MCP self-test + sdk tests green
- [ ] tree-sitter 0.25 caps raised, graph reindexed, extractor parity tests green
- [ ] Full `pytest tests/ -q` + UI build final sweep green

## Work Log
- 2026-05-31 [claude]: Status transitioned to complete via cos task-done.
