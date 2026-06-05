---
name: codebase-explorer
tier: exploration
domain: [universal]
description: Conceptual code-reading for unfamiliar areas — trace a feature, follow a data flow, understand a domain. Use when the question is conceptual ("how does auth work?", "what happens when a user buys X?"); for symbol-precise queries (callers, blast radius, rename) use graph-explorer instead. The two are complementary — codebase-explorer reads code as prose; graph-explorer queries it as a graph.
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
argument-hint: "Conceptual area to explore (e.g., 'auth flow', 'payment integration', 'blog comments')"
last_reviewed: "2026-05-11"
---

Explore the specified conceptual area of the codebase and produce a structured map. **Boundary with [graph-explorer](../graph-explorer/SKILL.md):**

| Question shape | Use |
|---|---|
| "How does X work end-to-end?" | codebase-explorer |
| "What happens when a user does Y?" | codebase-explorer |
| "Where does this domain live?" | codebase-explorer |
| "What calls function `foo`?" | graph-explorer (`cos_graph_references`) |
| "What breaks if I rename `Bar`?" | graph-explorer (`cos_graph_rename_plan`) |
| "Blast radius of changing `baz`?" | graph-explorer (`cos_graph_impact`) |

codebase-explorer always *consults* graph-explorer for symbol-precise sub-questions during a conceptual walk — they compose, they don't compete.

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

## Tooling

Get a file's structure in one call (stdlib, no graph/MCP needed):
`python3 scripts/outline.py src/foo.py`

## See also

- [references/reading-strategies.md](references/reading-strategies.md) — top-down reading, conceptual vs structural, orientation moves.
- [assets/reading-checklist.md](assets/reading-checklist.md) — the orientation gate.
- [graph-explorer](../graph-explorer/SKILL.md) — switch here for symbol-precise queries (callers, blast radius, rename).
- [search](../search/SKILL.md) — grep for literals; [technical-writing](../technical-writing/SKILL.md) — write the model down.
