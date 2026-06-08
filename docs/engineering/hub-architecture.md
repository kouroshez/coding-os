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

## Dashboard live agents (`/api/sessions/active`)

`DashboardPage` derives its "agents live" count from `/api/sessions/active` — one row per `.coding-os/<agent>/sessions/<sid>.json`. Each row carries:

| Field | Meaning |
|---|---|
| `state` | `active` (tool/prompt ≤30s) · `present` (≤300s TTL) · `idle` (pid alive, activity stale) · `offline` (pid dead) · `ended`. |
| `is_current` | `true` when the row's `session_id` equals the agent's `session-id` marker — i.e. this is the agent's live session, not a recycled-PID leftover. |

The dashboard counts `active`/`present` rows **plus** any `is_current` row whose pid is alive. Without the `is_current` clause a read-only session (verify/git/pytest, no `Write`/`Edit`) aged past the 300s TTL would classify `idle` and be silently dropped — the agent shows as working while the HUD reads "no agent running". `agent-presence.sh` also fires on `PostToolUse Bash` so such sessions refresh `last_tool_at` and mostly never reach `idle` in the first place; `is_current` is the defense-in-depth backstop.

### Live-agent context window (`context_pct`)

`/api/presence/agents` reports each Claude agent's context-window fill as
`context_pct`. The token counts come from the Stop path: `agent-presence.sh`
passes the runtime's `transcript_path` to `_helpers/presence_write.py`, which on
the `stop` event tails the **live** transcript for the last assistant `usage`
block, sums `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`,
and stamps `used_tokens` (+ `context_updated_at`) into `sessions/<sid>.json`.
`presence.py` divides `used_tokens` by the model's window (1M for a `[1m]` model
id, else 200K) to derive the percent. This is privacy-safe — only the aggregate
token count is stored, never transcript content — so it works without the opt-in
`COS_SNAPSHOT_TRANSCRIPT` snapshot. The snapshot tail remains a fallback, and the
value is **honest-null** (not fabricated) when no usage signal exists, e.g. for
non-Claude adapters.

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

The SPA is organized into two nested hubs, each served at a global path and a
`/p/:slug/` project-scoped path. Legacy flat routes (`/dashboard`, `/board`,
`/search`, `/doctor`, `/logs`, `/observability`, `/sessions`, `/audits`,
`/settings`) redirect into the hubs (see `App.tsx`).

| Route | Component | Backend endpoints |
|---|---|---|
| `/` | `HubHome` | `/api/hub/*` |
| `/workspace` · `/p/:slug/workspace` → `chat` / `board` / `search` | `WorkspacePage` → `ChatLanding` / `CosBoardPage` / `SearchPage` | cognition+board · `/api/cognition/*` · `/api/board/*` · `/api/search/*` |
| `/diagnostics` · `/p/:slug/diagnostics` → `overview` / `doctor` / `logs` / `observability` / `sessions` / `audits` / `memory` / `settings` | `DiagnosticsPage` → `DashboardPage` (Overview) / `DoctorPage` / `LogsPage` / `ObservabilityPage` / `SessionsPage` / `AuditsPage` / `MemoryPage` / `SettingsPage` | telemetry (cost/board/traces/agents) · `/api/health` + `/api/health/db` · `/api/logs/*` · `/api/hooks/*` + `/api/observability/*` · `/api/sessions/*` · `/api/audits/*` · `/api/settings` |

The chat-first landing replaced the Mission-Control dashboard at `/workspace`;
the dashboard's telemetry widgets were re-homed to **Diagnostics › Overview**
(`DashboardPage` now serves that route) and the orphan `/workspace/dashboard`
route was removed (TASK-250). Legacy `…/dashboard` deep-links redirect to
Diagnostics › Overview; a bare `/p/:slug` redirects to the chat landing.
| `/p/:slug/graph[/:rootUid]` | `GraphPage` | `/api/graph/*` |
| `/p/:slug/cognition[/:sessionId]` | `CognitionPage` | `/api/cognition/*` |

Both hubs render at a global (unscoped) path and a `/p/:slug/` project-scoped
path; **Graph** and **Cognition** are project-scoped only. The Doctor page reads
`/api/health` + `/api/health/db` (per-uvicorn) and parses Prometheus client-side.

Chart primitives (`Sparkline`, `BarList`, `Gauge`, `StatTile`) live in [src/core/web/ui/src/lib/charts.tsx](../../src/core/web/ui/src/lib/charts.tsx) — hand-rolled inline SVG, no chart library dependency. Prometheus text parser at [src/core/web/ui/src/lib/prometheus-parse.ts](../../src/core/web/ui/src/lib/prometheus-parse.ts).

## Ports

| Port | Service | Lifetime |
|---|---|---|
| **9188** | Hub FastAPI (uvicorn) — serves `/api/*` + SPA from `src/core/web/ui/dist/` | always, singleton per user |
| **5173** | Vite dev server (HMR) — edit-save-see-in-browser loop | only when `make ui-dev` is running |

5173 **proxies** `/api` and `/health` to 9188, so the backend stays
single-homed. No conflict between the two — they serve different
purposes and you rarely run both at once.

## Command palette (Cmd/Ctrl+K)

`CommandPalette` (mounted in `AppShell`, built on the shared `Modal`) reserves
Cmd/Ctrl+K to open a fuzzy jump-to over **projects** (`/api/hub/projects`),
**tasks** (`/api/board/list` cards) and **chat sessions** (`/api/cognition/chats`)
in the current project. Sources are fetched on open; the input filters them
(case-insensitive substring, pure `filterCommandItems`); ↑/↓ move the active row
and Enter navigates (project → its chat landing, task → the board, chat → that
session). The signature Linear/Vercel/Claude-desktop affordance; traces/full
search are a fast-follow.

## Attention model (tab badge + Notification API)

An autonomous agent runs long and then finishes or stalls — the human must not
have to stare at the tab. `AttentionBell` (mounted in `AppShell`) subscribes via
`useEventStream` to `dispatch-completed` / `agent-blocked` / `needs-input` and,
when the tab is **unfocused** (`document.hidden`), raises an unread count that
drives a tab-title badge (`(N) Coding OS Hub`), a favicon dot, and — once the
user has opted in — a `Notification`. A bell dropdown keeps an in-app activity
feed. The count clears on refocus (`focus` / `visibilitychange`). Only
`dispatch-completed` has a producer today; `agent-blocked` / `needs-input` are
subscribed forward-compatibly (dormant until the Stop/PreToolUse path emits
them — a fast-follow backend producer), so no event name is invented client-side.

## RTL readiness (app-level dir seam)

The Hub is LTR by default but RTL-ready (the owner authors Persian). A single
app-level seam — `applyHubDirection()` in
[src/core/web/ui/src/lib/direction.ts](../../src/core/web/ui/src/lib/direction.ts),
called once from `main.tsx` — sets `<html dir>` from `VITE_HUB_DIR` (default
`ltr`). Flipping the whole UI to RTL is therefore **config, not a rewrite**:
set `VITE_HUB_DIR=rtl` and rebuild. The visual layer is already direction-safe —
`index.css` ships `[dir="rtl"]` + the Vazirmatn font, and the primitives
(`Modal`, `SubNav`) use logical Tailwind utilities (`inset-*`, `justify-*`,
`*-inline-*`) that mirror automatically. User/agent-authored prose containers
use `dir="auto"` so a Persian message renders RTL even while the chrome stays
LTR.

## Onboarding readiness (chat-landing hero)

`GET /api/cognition/onboarding-status` tells the chat landing whether the
project still needs onboarding. It is **placeholder-scan first**: the scaffold
PRD (`docs/prd/01-snapshot-vision.md`) ships with `_TODO:` markers, so any
remaining `_TODO:` in `docs/prd/**` means onboarding is incomplete. An explicit
`.coding-os/onboarding.json` with `{"completed": true}` is an optional override
that short-circuits the scan. When `docs/prd/` has no scaffold at all the project
is treated as complete (nothing to onboard). `ChatLanding` renders a dismissible
`OnboardingCard` hero when `complete === false`; its CTA starts the docs-scoped
onboarder session (`/api/cognition/onboard`, TASK-246) so authoring is confined
to `docs/`.

## Per-project hook/skill overrides (Config toggles)

Hooks are **live symlinks** shared by every project, so a per-project enable/
disable cannot live in the global `registry.yaml` (editing it de-armours every
consumer). Instead each project carries `.coding-os/hook-overrides.json` /
`.coding-os/skill-overrides.json` (`{"disabled": ["<id>", …]}`).

The SSOT is [src/cli/project_overrides.py](../../src/cli/project_overrides.py):
it reads the override, drops any **safety-category** hook (safety hooks are
NON-disableable — the Config UI greys them and the primitive refuses them), maps
the remaining ids → script basenames, and writes the derived runtime allowlist
`.coding-os/disabled-hook-scripts` (one safe-to-skip basename per line).

Enforcement is at **runtime** — the architecturally correct point for a shared
symlink (the same physical script serves all projects, so only a runtime check
can vary per project): `cos-env.sh`, sourced at the top of every hook, sees the
calling hook's basename in `disabled-hook-scripts` and `exit 0`s the hook before
its body runs. The check is a single `stat` when no override file exists (the
common case), and a safety hook can never appear in the derived list, so it can
never be skipped. Toggling a hook is instant — no re-render, no re-install.

## Create a project from the UI (init route + wizard)

A user can scaffold a brand-new project from the Hub without the CLI. Two
hub-global endpoints back the **New Project** wizard on `HubHome`:

- `GET /api/hub/stacks` — the installable stack grid, data-driven from
  `src/templates/*/stack.yaml` via `load_stack_registry` (Rule 11 — no
  hardcoded stack list). Returns `{id, label, category}` per stack.
- `POST /api/hub/registry/init` — runs `cos init --name … --project-dir …
  --template … --agent claude --yes --no-index --format json` in a
  subprocess with a timeout. It is the **highest-severity new surface**
  (writes the filesystem), so it sits behind the localhost security gate
  below, and validates before spawning: the name against
  `^[a-z0-9][a-z0-9._-]{0,63}$`, the parent dir exists, the target does not
  already exist, and the target is neither the meta-repo nor nested inside a
  registered project. `cos init` registers the project itself on a clean exit;
  a failed init leaves nothing (the partial target dir is removed). The
  wizard (location chips + name→slug preview + stack grid) lives in `HubHome`
  on the shared `Modal`.

## Localhost security gate (Origin/Host allowlist + CSRF)

The hub binds `127.0.0.1` but is **unauthenticated** — any page the user's
browser visits can issue requests at `127.0.0.1:9188`. Once mutation routes
exist (registry add/scan/gc, and the filesystem-scaffolding `init` route),
two browser-mediated threats apply: **DNS rebinding** (a page on `evil.com`
rebinds its hostname to 127.0.0.1) and **CSRF** (a drive-by page POSTs using
the user's browser). `SecurityGateMiddleware` ([src/core/web/security.py](../../src/core/web/security.py)) closes both.

**Engagement rule — browser-evidence-gated.** The gate only engages for
requests that carry browser-origin evidence (an `Origin` or `Referer`
header). Non-browser clients (curl, server-to-server, MCP, the test client)
never present those headers and are *not* the CSRF/rebinding vector, so they
pass through untouched. This is why adding the gate breaks no existing
server-side test.

| Check | Applies to | Rule |
|---|---|---|
| **Origin allowlist** | state-changing methods (POST/PUT/PATCH/DELETE) on `/api/*` | if `Origin` is present, its hostname must be in the localhost allowlist (`localhost` / `127.0.0.1` / `::1` + `COS_WEB_ALLOWED_HOSTS`) → else `403` |
| **Referer fallback** | same | if `Origin` is absent but `Referer` present, the `Referer` hostname must be allowlisted → else `403` |
| **Host allowlist** | any request carrying Origin/Referer | the `Host` header hostname must be allowlisted (DNS-rebinding defense — a rebound page sends `Host: evil.com`) → else `403` |
| **CSRF double-submit** | state-changing methods | the gate issues a readable `cos_csrf` cookie (SameSite=Lax) on responses; when that cookie is present on a request, the `X-CSRF-Token` header must echo it → else `403`. The SPA's `api-client.ts` reads the cookie and sends the header automatically. |

The Origin allowlist is the cross-origin *guarantee*; the CSRF token is
same-origin defense-in-depth (it engages once the cookie exists, i.e. in the
same-origin production build — in cross-origin dev `:5173→:9188` the cookie
is not sent, and the Origin allowlist already vouches for `:5173`).

Escape hatch: `COS_WEB_CORS_ALLOW_ALL=1` (the existing wide-open opt-in) also
disables the security gate, for the rare non-localhost deploy where the
operator has accepted the risk.

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
