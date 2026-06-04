---
id: TASK-067
title: "Graph extractors to 10/10: Go call-graph, TS type-resolution+awaits+enum, Shell fallback parity, contracts fiber/gin group+handler, next.js pages-router+page routes, react component marking"
swimlane: infra
kind: feature
epic: null
labels: [graph_os, extractors, completeness, polyglot]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-03
completed: 2026-06-03
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-067: Graph extractors to 10/10: Go call-graph, TS type-resolution+awaits+enum, Shell fallback parity, contracts fiber/gin group+handler, next.js pages-router+page routes, react component marking

**Outcome (one sentence):** Go/TS/Shell extractors + contracts (fiber,gin,echo,nextjs,react) reach Python-gold parity on knowledge+accuracy. Real gaps closed (not feature-theater): Go AST same-file call edges; TS type-edge resolution to local/imported symbols + awaits + enum/namespace nodes; Shell regex-fallback local-call parity; contracts fiber/gin group-prefix per-variable correctness fix + route to handler edge; next.js pages-router API + page.tsx route detection; react function-component metadata. Each group adversarial-tested + graph_os matrix verified.

## Read First
- docs/playbooks/polyglot-extractor-roadmap.md
- src/core/graph_os/extractors/code_python.py
- src/core/graph_os/extractors/code_go.py
- src/core/graph_os/extractors/code_ts.py
- src/core/graph_os/extractors/contracts.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Go file where `func A()` calls a same-file `func B()` / `(r *T) M()`, **When** code_go extracts it, **Then** a `calls` edge sourced at A's func/method uid resolving to B's real uid (confidence ≥0.9) is emitted — matching Python same_scope behaviour.
- **Given** a TS function/method whose param or return type is a locally-declared or imported symbol, **When** code_ts extracts it, **Then** the `has_param_type`/`returns_type` edge targets the resolved local/imported uid (not always `code:external:unresolved:`), `await fn()` emits an `awaits` edge, and `enum`/`namespace` declarations emit nodes.
- **Given** a Shell script with an intra-file function call under the regex fallback (tree-sitter absent), **When** code_shell extracts it, **Then** a local `calls` edge is emitted (parity with the tree-sitter path).
- **Given** a Go file registering routes on multiple Fiber/Gin groups plus a route on the bare app, **When** contracts extracts it, **Then** each route gets the prefix of ITS OWN group variable (not "last group seen"), and the handler arg emits a route→handler edge.
- **Given** a Next.js pages-router API file (`export default function handler`) or a `page.tsx`, **When** contracts extracts it, **Then** the route is detected (currently only app-router named exports are).
- **Given** a React function component (PascalCase returning JSX), **When** code_ts extracts it, **Then** the function node carries `metadata.component=true`.
- **Given** all the above, **When** `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` runs, **Then** it is green (new adversarial tests included) and `cos graph-reindex` on the repo completes without regression.

## Work Log
- 2026-06-04 [claude]: Extractors to 10/10: Go same-file AST calls (func+receiver-method @0.9), TS type-edge resolution+awaits+enum/namespace, 
