---
name: react-vite-hub
tier: stack
domain: [frontend]
description: Use when authoring or modifying the meta-repo's Hub UI in src/core/web/ui/ — React 18 + Vite + TypeScript + Sigma.js graph canvas + zustand state. Covers the contract between FastAPI routes (src/core/web/routes/) and the SPA, env vars (VITE_*), build pipeline, hot-reload dev mode, and how the Hub UI proxies into per-project /api/p/<slug>/* endpoints. Pairs with frontend-fundamentals, a11y, and graph-explorer (when touching graph visualization).
last_reviewed: "2026-05-11"

---

# react-vite-hub

Purpose: Edit the Hub UI safely — the SPA at `src/core/web/ui/` that
serves `http://127.0.0.1:9188` and is the visual face of the entire
coding-os system. Without this skill, agents break the build,
introduce hydration mismatches, or invent endpoints that don't exist.

Read when: editing any of:
- `src/core/web/ui/src/**/*.{ts,tsx}` — components, pages, hooks, store.
- `src/core/web/ui/src/lib/api-client.ts` — the API contract.
- `src/core/web/ui/vite.config.ts`, `tailwind.config.js` — build config.
- `src/core/web/server.py`, `src/core/web/routes/**/*.py` — when changing API shape.

Skip when: editing tests (`*.test.ts`), pure docs, or `src/core/web/ui/dist/` (build output).

## Stack

```
React 18 + TypeScript + Vite + TailwindCSS + Sigma.js (graph canvas)
+ Graphology (graph data) + zustand (state) + react-router-dom
+ shadcn/ui-style component primitives in src/components/
```

## Architecture (single-page, single-server)

```
http://127.0.0.1:9188
    ├─ /api/<router>/*    ← FastAPI routes from src/core/web/routes/
    ├─ /api/stream/events ← SSE stream from src/core/web/routes/stream.py
    ├─ /                  ← Vite-built SPA (index.html → React)
    └─ /assets/*          ← Vite-emitted JS/CSS bundles
```

The SPA is served by FastAPI's `StaticFiles` mount at the root. Anything
the agent adds to the API must go in `src/core/web/routes/<area>.py`,
include the router in `src/core/web/server.py`, and be matched by a typed
client method in `src/lib/api-client.ts`.

## Hub propagation — multi-project

Each registered project is reachable via `/api/p/<slug>/*` — a thin
proxy that targets the same routes but scoped to that project's
`.coding-os/` state. UI uses `ProjectSwitcher` to set the slug; all
hooks read from `useProjectStore.getState().slug` before composing
URLs. NEVER hardcode a project path.

## Hard rules

### 1. URL is the source of truth

`react-router-dom` URL = source of truth for "which root node is selected,"
"which project is active," "which view." Components read URL, mutators
call `useNavigate()` — bidirectional `useEffect` pairs cause render
loops (TASK-117).

### 2. SSE for live data

Real-time hooks/cognition/board updates flow through
`/api/stream/events` (Server-Sent Events). Use `useEventStream(channel)`
hook in `src/lib/use-event-stream.ts`. NEVER poll.

### 3. Sigma.js + Graphology

Graph rendering uses Sigma.js renderer over a Graphology graph instance.
Performance-sensitive — use:
- `useSigma` hook for instance lifecycle (`src/features/graph/useSigma.ts`).
- Server-paginated subgraphs via `cos_graph_export(format="json", root_uid=...)`
  — never load the full 30K-node graph client-side.

### 4. zustand stores live in `src/store/`

Each domain has its own store: `graph-store.ts`, `board-store.ts`,
`project-store.ts`. NO Redux, NO Context-only state, NO MobX. Stick
with zustand for consistency.

### 5. TailwindCSS tokens, not raw colors

Use CSS custom properties (`var(--cos-border)`, `var(--cos-panel)`)
defined in `src/index.css` + `cos-board-tokens.css`. NEVER inline hex.

### 6. Type-safe API client

`src/lib/api-client.ts` exposes typed methods (`api.graph.query(q)`,
`api.board.list()`, …). Add new endpoints by extending this file.
Components should NEVER `fetch()` directly.

## Pre-edit moves

1. `cos_graph_resolve("react component or feature name")` → see existing.
2. `cos_graph_context(uid, depth=1)` → component neighbours.
3. Check `src/lib/api-client.ts` — does the endpoint already exist?
4. THEN edit.

## Build / dev

```bash
make ui-dev      # vite dev :5173 with HMR (proxies to FastAPI :9188)
make ui-build    # production build → src/core/web/ui/dist/
```

After a UI change: `make ui-build` to refresh the static bundle that
the FastAPI singleton serves at `http://127.0.0.1:9188`. The dev
server is for iteration only.

## Anti-patterns

- **Inline `<style>` blocks** — use Tailwind utilities or CSS variables.
- **`useEffect` with empty deps that calls `setState`** on first render → infinite loops.
- **Hard-coded project slug** — always read from `useProjectStore`.
- **Loading the full graph** — paginate via `cos_graph_export` with `root_uid`.
- **`fetch('/api/...')` directly** — extend `api-client.ts` instead.
- **Duplicating component structure** — check `src/features/graph/` for graph utilities, `src/components/` for primitives, `src/layout/` for shells.

## A11y baseline

- Every interactive element has a focus ring (Tailwind `focus-visible:ring-2`).
- Modal/dialog components use `@radix-ui/react-dialog` for keyboard trap.
- Color contrast — verify with Lighthouse; tokens in `cos-board-tokens.css` already pass AA.

## Tooling

Flag Vite client-env footguns (process.env / non-VITE_ vars undefined in the build):
`python3 scripts/check_vite_env.py src/core/web/ui/src/**/*.tsx`

## See also

- [assets/hub-ui-checklist.md](assets/hub-ui-checklist.md) — the Hub-UI gate (env, API contract, quality).
- [src/core/web/ui/README.md](../../../../core/web/ui/README.md) (when present)
- [docs/engineering/hub-architecture.md](../../../../docs/engineering/hub-architecture.md)
- [src/core/skills/frontend-fundamentals/SKILL.md](../../../../core/skills/frontend-fundamentals/SKILL.md)
- [src/core/skills/a11y/SKILL.md](../../../../core/skills/a11y/SKILL.md)
