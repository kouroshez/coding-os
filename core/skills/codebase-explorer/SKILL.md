---
name: codebase-explorer
description: Explore and map codebase structure for unfamiliar areas. Use when you need to understand how a feature works, trace a data flow, or map dependencies before making changes.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
argument-hint: "Area to explore (e.g., 'auth flow', 'payment integration', 'blog comments')"
---

Explore the specified area of the codebase and produce a structured map.

## Process

1. **Graph gate (Phase I)** — If the query is an identifier-shaped symbol
   (`camelCase`, `snake_case`, `Class.method`, `TASK-NNN`, dotted path),
   try `cos_graph_query` first. It is faster + more accurate than grep
   for named symbols AND returns confidence-scored edges. Fall back to
   grep only if the graph returns zero hits (fresh repo, unindexed file)
   or the query is conceptual ("auth flow", "money handling").
2. **Entry points** — Use Grep to find the main files related to the topic.
3. **Trace the flow** — Read key files, follow imports. When symbols
   cross file boundaries, prefer `cos_graph_context(uid, depth=1)` over
   chasing imports by hand — it returns the neighbourhood in a single
   MCP call.
4. **Dependencies** — Identify what this area depends on (models,
   services, external APIs). For impact analysis, use
   `cos_graph_impact(uid, direction="downstream")` — the plan's
   Formula-2 Step-10 tool.
5. **Test coverage** — Use Glob to find related test files. Graph edges
   of type `tested_by` (when present) point directly at them.

## Output Format

Return a structured summary:

```
## [Area Name] — Codebase Map

### Entry Points
- file:line — description

### Data Flow
source → transform → destination

### Key Files
- path — responsibility

### Dependencies
- internal: models, services used
- external: APIs, packages

### Test Coverage
- test files found
- gaps identified

### Risks
- anything fragile, tightly coupled, or undocumented
```

Do NOT make any changes. This is read-only exploration.
