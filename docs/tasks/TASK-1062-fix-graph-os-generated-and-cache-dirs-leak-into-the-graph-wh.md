---
id: TASK-1062
title: "fix(graph_os): generated and cache dirs leak into the graph when .gitignore misses them"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1062: fix(graph_os): generated and cache dirs leak into the graph when .gitignore misses them

**Outcome (one sentence):** Build, cache and dependency output of the shipped stacks (Expo, RN Android/iOS, Flutter, Python venvs, JS tool caches, gradle/maven wrappers) never enters the graph, even in a project whose .gitignore does not list them.

## Read First
- docs/engineering/graph_os-queries.md

## Repro Steps
1. Build a scratch tree with those dirs, each holding one .ts and one .py file, and no .gitignore.
2. `walk_local(tree)` → 35 generated dirs are collected (LEAK list in the session probe).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a tree with .expo, .yarn, coverage, venv (pyvenv.cfg), DerivedData, android/app/.cxx, .dart_tool, android/gradlew and no .gitignore **When** walk_local runs **Then** only the hand-written source files are collected
- **Given** a git-tracked `out/` or `coverage/` source folder **When** walk_local runs **Then** it is still indexed

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
