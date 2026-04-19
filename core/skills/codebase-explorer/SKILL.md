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

1. **Entry points** — Use Grep to find the main files related to the topic
2. **Trace the flow** — Read key files, follow imports, map the data flow
3. **Dependencies** — Identify what this area depends on (models, services, external APIs)
4. **Test coverage** — Use Glob to find related test files

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
