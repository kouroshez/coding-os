<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-13 -->
# Hub Architecture

Purpose: Canonical contract for the singleton hub daemon (FastAPI + React SPA on :9188), per-project routing via `/api/p/<slug>/*`, and the propagation matrix for live symlinks (hooks/rules/skills/commands).
Read when: editing `src/core/web/`, `src/cli/hub_*.py`, or any code that registers a project with the hub.

> Nav: [docs/](../) · [engineering/](./)

One uvicorn process, one browser tab, every coding-os project. This doc
explains where state lives, how changes propagate, and which port serves
what.

## Three address spaces

| Location | Holds | Mutated by |
|---|---|---|
| **Meta repo** `/Users/<you>/.../coding-os/` | `src/core/` + `src/adapters/` + `src/templates/` + `src/cli/` (source of truth) | humans + agents edit directly |
| **Hub state** `~/.coding-os/` | `registry.json`, `hub.pid`, `hub.log`, `groups/` | `cos registry`, `cos hub`, `cos graph-groups`, first-run bootstrap |
| **Project state** `<repo>/.coding-os/` | `coding-os.db`, `.agent`, `<agent>/session-id`, `<agent>/sessions/*.json`, `.hooks.log`, `installed-manifest.json` | hooks, MCP server, `install.sh`, CLI commands run inside the project |

**`~/.coding-os/` does NOT hold code.** The hub loads every byte of
`src/core/` and `src/adapters/` directly from the meta repo — `uv tool install
--editable .` links the `cos` bin to the repo source. Moving or deleting
the repo breaks the hub; `~/.coding-os/` by itself is useless.

## Scrumban board API — live agents (`/api/board/list`)

Successful board list payloads include:

| Field | Meaning |
|---|---|
| `agent_states` | Per adapter id: `active` / `present` / `offline` (from `.coding-os/<agent>/sessions/*.json` written by `agent-presence.sh`, with DB fallback). |
| `agent_manifest` | Rows built from `src/adapters/*/adapter.yaml` (id, label, `hub_glyph`, `hub_color`, session prefix) plus a synthetic **`human`** row — no hardcoded adapter tuple in Python or React. |
| `presence_scope` | Today always `per_project`: presence files are read only under the **currently scoped project root** (the slug passed to `/api/p/<slug>/…` or `COS_PROJECT_ROOT`). |
| `cursor_model` | Optional display-only string: first line of `.coding-os/cursor/.model` when the file exists. **Not** used for green/red presence (runtime stays `COS_AGENT=cursor`). |

**Not implemented:** aggregating “this adapter is active in *any* registered repo” under `~/.coding-os/`. That would need a separate global store or a registry walk; the field `presence_scope` leaves room to extend the contract later.

## Per-project backend keying (graph + DB)

One uvicorn process serves every registered project. To prevent the first project's SQLite handle from leaking into another project's response, every layer that opens a database now keys its singleton by the **resolved DB path**, not by a process-global slot.

| Layer | Cache key | Rebuild trigger |
|---|---|---|
| `src/core/thinking_os/database.py::_active_project_root` (ContextVar) | per-request | `ProjectScopeMiddleware.dispatch` sets/resets via `set_active_project_root` / `reset_active_project_root` |
| `src/core/graph_os/tools/graph.py::_BACKEND_SINGLETONS: dict[str, GraphBackend]` | resolved DB path (via `_current_db_key()`) | first miss for a given path opens a fresh backend |
| `src/core/graph_os/backend.py::_BACKEND_CACHE` | `(choice, resolved_db_path)` tuple | same — different project → different cache key |
| `src/core/thinking_os/database.py::resolve_db_path(project_root=None)` | inspects ContextVar when no arg passed | falls back to `$COS_DB_PATH` → `DEFAULT_DB_PATH` for MCP / CLI callers |

Contract:
- `/api/p/<slug>/*` requests resolve via the registry, set both ContextVars (web-side `_current_project` + DB-side `_active_project_root`), then reset on `finally`.
- MCP server and CLI callers never set the DB-side CV → `resolve_db_path()` returns `DEFAULT_DB_PATH` → behavior unchanged.
- Tests that monkey-patch `graph_os.tools.graph._BACKEND_SINGLETON` (legacy slot) still work — when non-None it short-circuits the per-project lookup.

`reset_backend()` (test-only) clears **both** the legacy slot and every entry in `_BACKEND_SINGLETONS`.

## SPA pages — primary nav

| Route | Component | Backend endpoints |
|---|---|---|
| `/` | `HubHome` | `/api/hub/*` |
| `/dashboard`, `/p/:slug/dashboard` | `DashboardPage` | aggregates board + presence |
| `/board`, `/p/:slug/board` | `CosBoardPage` | `/api/board/*` |
| `/graph`, `/p/:slug/graph[/:rootUid]` | `GraphPage` | `/api/graph/*` |
| `/search`, `/p/:slug/search` | `SearchPage` → `UnifiedSearch` | `/api/search/*` |
| `/cognition[/:sessionId]`, `/p/:slug/cognition[/:sessionId]` | `CognitionPage` | `/api/cognition/*` |
| `/observability`, `/p/:slug/observability` | `ObservabilityPage` | `/api/hooks/{recent,stream,list}`, `/api/observability/timeline`, `/api/board/{daily,wip,retro}` |
| `/sessions`, `/p/:slug/sessions` | `SessionsPage` | `/api/sessions/active`, `/api/observability/sessions` |
| `/doctor` (global, not scoped) | `DoctorPage` (Overview · Health & charts · Maintenance) | `/health`, `/metrics` (client-side Prometheus parse) |
| `/settings` (global) | `SettingsPage` | `/api/settings` |

`Doctor` is intentionally **global**, like `Settings` — backend health is per-uvicorn, not per-project. Every other nav item is project-scoped via the `/p/<slug>/` middleware rewrite.

Chart primitives (`Sparkline`, `BarList`, `Gauge`, `StatTile`) live in [src/core/web/ui/src/lib/charts.tsx](../../src/core/web/ui/src/lib/charts.tsx) — hand-rolled inline SVG, no chart library dependency. Prometheus text parser at [src/core/web/ui/src/lib/prometheus-parse.ts](../../src/core/web/ui/src/lib/prometheus-parse.ts).

## Ports

| Port | Service | Lifetime |
|---|---|---|
| **9188** | Hub FastAPI (uvicorn) — serves `/api/*` + SPA from `src/core/web/ui/dist/` | always, singleton per user |
| **5173** | Vite dev server (HMR) — edit-save-see-in-browser loop | only when `make ui-dev` is running |

5173 **proxies** `/api` and `/health` to 9188, so the backend stays
single-homed. No conflict between the two — they serve different
purposes and you rarely run both at once.

## Propagation matrix — edit X, how does it reach consumer projects?

| Change | Propagates to the meta repo itself | Propagates to consumer projects |
|---|---|---|
| `src/core/hooks/*.sh`, `src/core/rules/**`, `src/core/skills/**`, `src/core/commands/**` | instantly (symlinked by `install.sh`) | instantly (same symlinks in every project) |
| `src/core/hooks/registry.yaml` | `make sync` (re-renders `src/adapters/*/[settings\|hooks].template.json`) | `cos sync-all` (calls each adapter's `install.sh` per project) |
| `src/adapters/<agent>/adapter.yaml` field | `make sync` | `cos sync-all` |
| `src/core/thinking_os/database.py` schema (new migration) | next `cos`/`hub` invocation runs `init_db` | `cos sync-all` forces `init_db` on every project's DB |
| `src/core/web/ui/src/**` (SPA source) | `make ui-build` → `dist/` → hub serves new bundle on next request (hard-refresh browser) | same — all projects share one SPA bundle served by the hub |
| `src/core/web/routes/**` (FastAPI) | hub daemon auto-reloads if started with `--reload`, otherwise `cos hub stop && cos hub start` | same |
| `src/cli/**` | `uv tool install --editable .` pointed at this repo, so next `cos` invocation picks it up | same |

## "I edited the UI, why don't I see it?"

Three things must line up:

1. **Build** — `src/core/web/ui/src/` is TypeScript source. The browser sees
   `src/core/web/ui/dist/`. Run `make ui-build` (≈3s) OR keep `make ui-dev`
   running in a separate terminal (HMR on 5173).
2. **Hub is up** — `cos hub status` must show `running`. The hub mounts
   `dist/` via FastAPI StaticFiles; without it there's nothing to serve.
3. **Browser cache** — hard-refresh (Cmd/Ctrl-Shift-R). Bundle names are
   content-hashed (`index-<hash>.js`) so regular reloads pick up new
   bundles automatically, but service-worker-like caches warrant a
   hard-refresh during iteration.

`~/.coding-os/` never enters this loop. It is state, not code.

## Symlink health

Every consumer project's `.claude/hooks/*.sh` / `.cursor/hooks/*.sh` /
`.codex/hooks/*.sh` is a symlink to `src/core/hooks/*.sh` in this meta repo.
Edits here reach every project **instantly** — no `cos update` needed.

If the meta repo is moved, those symlinks become dangling. Detect and
repair:

```bash
cos hub status                # summary line will say "Symlink health: broken in [...]"
cos sync-doctor               # per-project JSON report
cos sync-doctor --repair      # re-run install.sh on each broken project
```

## Commands cheat-sheet

| Task | Command |
|---|---|
| Start the hub (first time) | `cos hub start` |
| Stop / restart | `cos hub stop` then `cos hub start` |
| Status + meta repo + symlink health | `cos hub status` |
| Tail hub log | `cos hub logs -n 100` |
| Run as background service | `cos service install` (launchd / systemd user) |
| List registered projects | `cos registry list` |
| Add an existing project | `cos registry add <path>` |
| Discover projects on disk | `cos registry scan <root>` |
| Prune dead entries | `cos registry gc` |
| Remove a project | `cos registry remove <slug>` |
| Push edits to every registered project | `cos sync-all` |
| Fix broken symlinks | `cos sync-doctor --repair` |
| SPA iteration (HMR) | `make ui-dev` (→ http://127.0.0.1:5173) |
| SPA production build | `make ui-build` |

## Why this split makes sense

- **Code lives with the repo** so git history is the single source of truth
  and `uv tool install --editable .` gives you zero-copy development.
- **Hub state** is a per-user singleton — one registry, one daemon, one
  browser tab — but the registry is just a list of pointers, no data.
- **Project state** stays in each project because agents mutate it
  constantly (sessions, task history, hook log) and those mutations
  must not escape the project boundary.

The result: you edit `src/core/**`, every registered project sees it via
symlink or `cos sync-all`; you edit `src/core/web/ui/**`, one SPA build
updates every project's panel. No fanned-out `.coding-os/` copies to
keep in sync.
