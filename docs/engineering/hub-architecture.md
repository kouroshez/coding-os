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

Consumed by the dashboard's Live-agents card (TASK-324): each session row
renders a `ctx N%` badge (`DashboardPage.tsx::ContextPctBadge`, green/amber/red
at 60/85%), with an explicit `ctx ?` state when the value is honest-null —
never a fabricated 0%.

### Live-agent owning project (`slug`) — home-level click-through (TASK-435)

`/api/presence/agents` stamps each agent with `slug`: the owning project's
registry slug, derived from the resolved `current_project_root()` via
`cli.registry` (`_derive_slug`, matched against `load_registry()`). Home-level
surfaces render at the **unscoped** `/` route, where `useScopedLink` has no
`/p/<slug>/` segment to read; they therefore build the chat/trace link
**explicitly** from `agent.slug` → `/p/<slug>/cognition/<sdk_uuid>?view=chat`,
NOT via `useScopedLink` (which is for already-scoped contexts and silently
degrades to the unscoped `/cognition/...` form → `NeedProjectPage`, the project
picker, never the transcript — the TASK-435 bug that violated TASK-194's
click-through DoD). `slug` is honest-null when no registry slug resolves; the
Live-agents panel then falls back to the in-place `AgentDetailModal` rather than
emitting a picker-bound link.

Presence stays `per_project`-scoped (§ Scrumban board API): the home panel shows
the Hub launch-cwd project's agents, each carrying that project's slug. A true
cross-project roster (registry walk + per-project DB scoping) remains the
documented extension the `presence_scope` field leaves room for — filed as a
follow-up, not folded into TASK-435.

## Per-project backend keying (graph + DB)

One uvicorn process serves every registered project. To prevent the first project's SQLite handle from leaking into another project's response, every layer that opens a database now keys its singleton by the **resolved DB path**, not by a process-global slot.

| Layer | Cache key | Rebuild trigger |
|---|---|---|
| `src/core/thinking_os/database.py::_active_project_root` (ContextVar) | per-request | `ProjectScopeMiddleware.dispatch` sets/resets via `set_active_project_root` / `reset_active_project_root` |
| `src/core/graph_os/tools/graph.py::_BACKEND_SINGLETONS: dict[str, GraphBackend]` | resolved DB path (via `_current_db_key()`) | first miss for a given path opens a fresh backend |
| `src/core/graph_os/backend.py::_BACKEND_CACHE` | `(choice, resolved_db_path)` tuple | same — different project → different cache key |
| `src/core/thinking_os/database.py::resolve_db_path(project_root=None)` | bound `_active_project_root` ContextVar wins first | else `$COS_DB_PATH` → explicit arg → cwd-walk |

Resolution precedence (SSOT — `resolve_db_path`): **bound scope → `$COS_DB_PATH` → explicit arg → cwd-walk.** The bound per-request scope is checked *before* the ambient `$COS_DB_PATH` because the Hub inherits a `$COS_DB_PATH` from whichever project directory it was launched in; if the env won, every `/api/p/<slug>/*` request would leak onto that one project's DB regardless of the slug.

Contract:
- `/api/p/<slug>/*` requests resolve via the registry, set both ContextVars (web-side `_current_project` + DB-side `_active_project_root`), then reset on `finally`. The bound `_active_project_root` overrides any ambient `$COS_DB_PATH` for the life of that request.
- MCP server and CLI callers never set the DB-side CV → the bound branch is skipped → `resolve_db_path()` honors `$COS_DB_PATH` (or the explicit arg / cwd-walk) exactly as before → behavior unchanged.
- The final `cwd-walk` step never anchors on `$HOME` as a project: `~/.coding-os/` is the **global hub state dir** (§ Three address spaces), never a project root. `_find_project_root_from_cwd` returns `None` at the bare-`$HOME` boundary; `resolve_db_path()` falls back to cwd (non-raising, so callers that only catch `ImportError` stay intact), and **`init_db` refuses to CREATE a project DB inside `~/.coding-os`** — the guard sits at the mkdir chokepoint, which also closes the `DEFAULT_DB_PATH` default path. A real subdirectory under `$HOME` still resolves to cwd.
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

## Graph community-map home (focus+context, TASK-407)

> **Status — needs a human visual review.** The layout below is the InfraNodus/Bloom-style default for the no-root Graph home; the blind switch in TASK-406 was visually rejected (only 2 community nodes surfaced at a 500-node budget). This pass fixes the budget allocation and the de-emphasis styling but the on-canvas result has not yet been signed off by the user.

The no-root Graph home renders `cos_graph_export(mode="processes")` as a community map: each Louvain community is a labelled colored group with its top hubs, and non-focus member nodes are de-emphasised so the canvas reads as a subsystem map, not a flat blend sample.

**Per-community budget reservation** (`_export_processes` in [src/core/graph_os/tools/graph.py](../../src/core/graph_os/tools/graph.py)): two passes instead of the old greedy walk. Pass 1 reserves one synthetic `community` header node per community (budget-capped). Pass 2 spreads the remaining budget as an **equal per-community member quota** (`member_budget // headed_count`, floor 1) so a single 400-member cluster can no longer starve the rest. At `max_nodes=500` every community above `min_size` surfaces at least its header — the TASK-406 regression guard (`test_at_least_six_community_nodes_surface`, `test_budget_reserved_across_communities`).

**De-emphasis styling** (`buildGraph` in [src/core/web/ui/src/features/graph/graph-adapter.ts](../../src/core/web/ui/src/features/graph/graph-adapter.ts), wired by [GraphCanvas.tsx](../../src/core/web/ui/src/features/graph/GraphCanvas.tsx) passing `mode`): in `processes` mode community headers are the **focus** tier — forced label (`forceLabel`), full group color from [node-colors.ts](../../src/core/web/ui/src/lib/node-colors.ts), hub size — and member nodes are **context** — a small uniform dot, alpha-muted color (`#RRGGBBAA`), no forced label and no icon. Other modes (`auto`/`containment`/`dependencies`) are untouched.

## Hub settings contract (`/api/settings` ↔ `hub-settings.json`)

`GET/PATCH /api/settings` round-trips `$COS_STATE_DIR/hub-settings.json`
section-by-section; defaults live in `routes/settings.py::_DEFAULTS` and
unknown keys in the file survive untouched. Sections:

| Section | Keys | Consumers |
|---|---|---|
| `budget_cap` | `enabled`, `cap_usd` | dispatch budget gate |
| `trace_rotation` | `gzip_age_days`, `delete_age_days` | `auto-trace-rotate` hook |
| `task_closure` | `mode` | board closure enforcement |
| `model_routing` | `enabled` (default **false**), `orchestrator_model` | chat Auto picker (TASK-318) · agent-side routing hook (TASK-319) |
| `git_settings` | `enabled` (default **false**), `integration_branch` (`main`), `protected_branches` (`["production"]`) | pr-mode enablement — surfaced in **Config → Git** (per-project), not Settings (TASK-518) |

`git_settings.enabled=true` is the ONLY switch that turns pr-mode on: `cos-env.sh`
reads it from this project's `hub-settings.json` and exports `COS_GIT_WORKFLOW=pr`
(+ `COS_GIT_INTEGRATION_BRANCH` / `COS_GIT_PROTECTED_BRANCHES`) into every hook's
process env — the only place `branch-guard` / `block-shared-tree-edit` / the
`cos pr` executor can read the mode (an inline per-command override is broken).
Default-off = byte-identical to trunk. It lives under the **Config** tab (not the
hub-level **Settings** page) because it is per-project structure config; the
read-only git-state row comes from `GET /api/settings/git-state`. Full flow:
[docs/playbooks/pr-workflow.md § 1](../playbooks/pr-workflow.md) · [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md).

`model_routing.enabled=false` keeps the auto-routing feature fully inert
everywhere — no UI option, no injected context, no dispatch change. The
`orchestrator_model` value MUST be one of the ids the adapter→models SSOT
exposes (`/api/config/adapters`, sourced from `src/adapters/*/adapter.yaml::models`
— Rule 11: no model id literal lives in code). Kernel-side consumers read the
JSON file directly per call, so a settings change needs no server restart.

## Ports

| Port | Service | Lifetime |
|---|---|---|
| **9188** | Hub FastAPI (uvicorn) — serves `/api/*` + SPA from `src/core/web/ui/dist/` | always, singleton per user |
| **5173** | Vite dev server (HMR) — edit-save-see-in-browser loop | only when `make ui-dev` is running |

5173 **proxies** `/api` and `/health` to 9188, so the backend stays
single-homed. No conflict between the two — they serve different
purposes and you rarely run both at once.

## Concurrency model — never block the loop, never exhaust the pool

The hub is ONE uvicorn process with ONE asyncio event loop, serving every
project and every browser tab, while agent sessions concurrently write to
`coding-os.db` and the presence/log files the hub reads. Two hard rules keep
the panel responsive under that load (TASK-337 — multi-agent lockup):

**Server rule — `async def` only for truly-async work.** A handler that does
synchronous work (sqlite3, file reads, `subprocess.run` git calls, board_os /
graph_os tool calls) MUST be a plain `def` — Starlette runs it on the
threadpool, so a 5s locked-DB wait or an 8s git timeout stalls one worker
thread, not the event loop. `async def` is reserved for handlers that
genuinely await (Claude SDK chat streams, SSE generators). Inside SSE
generators, each poll tick's blocking work (DB watermark queries, task-file
glob/stat, presence snapshots, log tailing) runs via `asyncio.to_thread(...)`
— the async generator only sleeps, formats, and yields.

**Client rule — one shared `EventSource` per stream URL per tab.** Browsers
cap HTTP/1.1 at ~6 connections per origin, shared across ALL tabs; every SSE
connection holds one for its lifetime. UI consumers therefore never construct
`new EventSource(...)` directly — they acquire the ref-counted shared
connection from `src/lib/shared-event-source.ts` (keyed by resolved URL, so
per-project scopes and per-filter log streams get their own). Consumers
attach with `addEventListener` only (never `source.onopen = ...` — assignment
clobbers sibling consumers) and must handle attaching to an already-OPEN
source by checking `readyState`. A board tab holds 2 SSE connections
(`/api/stream/events` + `/api/hooks/stream`), not 4.

**Live dispatch observability (TASK-667).** A role-dispatch run (`sdk_dispatcher`)
tees each turn — `dispatch_started` / `dispatch_turn` / `dispatch_completed` — to
the append-only cognition trace sink (`thinking_os.tracing.emit`, keyed on the
dispatch's `sub_session_id`), partial-message text off by default
(`COS_DISPATCH_EVENT_CONTENT=1` to include it), fail-open so it never touches the
returned EvidenceBundle. `GET /api/cognition/trace/{session_id}/stream` tails that
jsonl over SSE (replays from the start, then live-tails — same `_drain_log` pattern
as `/api/hooks/stream`); `TraceTimeline` consumes it to append events in real time.
The dead `sdk_uuid` chat modal is resolved by a fallback in
`GET /api/cognition/chat/{session_id}`: when the live SDK session is gone, it serves
the dispatched sub-session's persisted `formula_dispatches.raw_transcript` instead of
404ing.

**Board stream event contract — a `task-updated` event means the status changed.**
`/api/stream/events` emits a `task-updated` row from two producers: the
authoritative DB watermark (`task_status_history`, `source: "db"`) and a
file-watch fallback for human edits not backed by a DB row (`source: "file"`,
`old_status: null`). The file-watch branch is **status-triggered, not
mtime-triggered**: a task `.md` is rewritten for many reasons that do not move
it (a `capture-work-log.sh` append per code Edit, a body edit), so `_poll_tick`
keeps a per-file status watermark (`_StreamState.last_status`) and emits only
when the parsed `status:` actually differs from the last seen value — an mtime
bump alone is silently absorbed. Without this guard the AGENT STREAM panel
stacks one phantom `? -> <status>` row per work-log append (TASK-411). The UI
(`useBoardStream.ts`) additionally collapses an incoming live event that is
identical to the newest row (same `taskId` + `newStatus` + `kind`) as
defence-in-depth; history-bootstrap rows already dedupe on their stable
`hist-…` id.

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
consumer). Instead each project carries `.coding-os/hook-overrides.json`
(`{"disabled": ["<hook-id>", …]}`). Skill opt-outs live in the project's
`.coding-os.yaml::disabled_skills` list (one store, written by `cos skill
disable`) — there is no separate `skill-overrides.json`.

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

**Skill overrides apply inline + at link time**: `cos skill disable <name>`
([src/cli/skill_commands.py](../../src/cli/skill_commands.py)) records the opt-out
in `.coding-os.yaml::disabled_skills` AND unlinks the skill's `SKILL.md` symlink
from every installed adapter immediately (no re-install needed). On a fresh
install / `cos update`, `install-adapter.sh` (step 6) re-reads the list via
`extract_disabled_skills.py` and skips + unlinks each disabled core/stack skill,
so the agent runtime stops loading its frontmatter description into every
session's system prompt (~150 tok per skill per session, paid again by every
subagent). Core and stack skills can both be disabled this way; re-enable with
`cos skill enable <name>`.

## Create a project from the UI (init route + wizard)

A user can scaffold a brand-new project from the Hub without the CLI. Two
hub-global endpoints back the **New Project** wizard on `HubHome`:

- `GET /api/hub/stacks` — the installable stack grid, data-driven from
  `src/templates/*/stack.yaml` via `load_stack_registry` (Rule 11 — no
  hardcoded stack list). Returns `{id, label, category, language}` per stack.
- `GET /api/hub/presets` / `GET /api/hub/adapters` /
  `GET /api/hub/skills` / `GET /api/hub/stacks/{id}/skills` — the wizard's
  read-only data sources (TASK-352/356/358): preset catalog, agent adapters,
  global skill catalog with provenance, and per-stack
  required/recommended/optional skill groups.
- `POST /api/hub/registry/validate-init` — dry-run validation + merged-config
  preview (swimlane union + reported conflicts). Shares
  `_validate_init_inputs` with the real init route (SSOT) and writes nothing.
- `POST /api/hub/registry/init` — runs `cos init --name … --project-dir …
  [--preset … | --template …×N] --agent <a[,b,…]> --yes --no-index
  --graph-index --format json` in a subprocess with a timeout. `--no-index`
  skips the heavy doc-RAG embedding (model load ~15s); `--graph-index`
  **overrides** the fact that `--no-index` would otherwise also skip the
  graph, so a Composer-created project still gets a built knowledge graph
  (AST walk, no embedding model) and its Graph tab is populated from the
  first session — never an empty canvas (unless the graph module is
  disabled at create time via `--disable-module graph`, which skips the
  build and leaves the Graph tab empty until `cos graph-reindex`). The
  graph build is bounded by
  `COS_INIT_GRAPH_TIMEOUT` (default 180s); on a very large repo it degrades
  to a gracefully-empty graph plus a `cos graph-reindex` HINT rather than
  hard-failing init, and the create subprocess timeout has headroom over
  that cap so a slow build never truncates a half-created project. Both
  init and validate-init accept
  `agents: list[str]` (a project may host several adapters, e.g.
  `.claude/` + `.codex/`) with a single `agent: str` kept for back-compat;
  `_resolve_agents` merges + de-dupes them and the preview echoes the resolved
  list. It is the **highest-severity new
  surface** (writes the filesystem), so it sits behind the localhost security
  gate below, and validates via the same `_validate_init_inputs` before
  spawning. An empty name auto-generates a temp slug (`proj-<6hex>`,
  "don't know yet"); the wizard's description seeds
  `docs/_meta/project-description.md` (TASK-364 intake) and `extra_skills`
  land in `.coding-os.yaml`. `cos init` registers the project itself on a
  clean exit; a failed init leaves nothing (the partial target dir is removed).
- `PATCH /api/hub/registry/{slug}` — slug rename (temp slug → real name; path
  untouched), backed by `cli.registry.rename_project`.
- **Job-based create (TASK-362):** `POST /registry/init` with
  `background: true` returns `{job_id}` immediately; the job
  (`src/core/web/init_jobs.py`, in-process + thread-safe) streams ordered
  phases (`validate → scaffold → adapters → docs-seed → register`) and a
  bounded log over `GET /api/hub/init-jobs/{id}/events` (SSE — replay then
  follow, so a browser refresh reattaches), with
  `GET /api/hub/init-jobs/{id}` snapshots and
  `POST /api/hub/init-jobs/{id}/cancel` (terminates the subprocess and
  removes the partial scaffold, reported as `cleanup.removed_dir`). Funnel
  counters (`cos_init_jobs_total{status=…}`) render into `/metrics`. The
  sync (non-background) form stays for programmatic callers.

**Composer (`OnboardingWizard.tsx`, TASK-419)** — a single screen replaces the
8-step wizard (TASK-358). Left column = choices (template preset/custom, name +
folder + a first-class description, and an *Advanced* disclosure for
multi-select agents + skills with tier/domain/description depth); right column =
a live "what you'll get" preview driven by `validate-init` (resolved stacks,
agents, board lanes as chips — not raw JSON, target path). The dominant path
(pick a preset → Create) is ~3 interactions. Stack-recommended *core* skills are
pre-selected into `extra_skills` (the scaffold only auto-links a stack's own
skill dirs, so curated core companions must ride `--skills`); unshipped
(`validated:false`) skills are filtered out of the selectable set. Built on the
shared `Modal` + `ActionPill` primitives and `--cos-*` tokens. The job-progress
view + cancel (TASK-362) are unchanged. **Module toggles at create (TASK-421):**
the Advanced section lists subsystem modules from `GET /api/hub/modules`
(`subsystems.yaml`); turning one off feeds `disabled_modules` →
`cos init --disable-module <id>` (kernel locked; the `tasks → docs` dependency
cascades in the UI and is re-checked by `set_module_enabled` at scaffold).
Modules stay adjustable post-create in Config.

**Project list never surfaces the global state dir.** `_derive_runtime_entry`
auto-lists the cwd as a project when it has `.coding-os/`, but `$HOME` and any
`.coding-os/` carrying the hub registry/pid (`registry.json` / `hub.pid` — the
global state dir, see § Three address spaces) are rejected, so the home dir
never appears as a phantom "live cwd" project.

## Localhost security gate (Origin/Host allowlist + CSRF)

> Full threat → control matrix (incl. the optional `COS_HUB_TOKEN` bearer
> mode and the init-argv allowlist): [hub-threat-model.md](hub-threat-model.md).

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
| **Bearer on reads (non-loopback)** | `GET /api/*` when `COS_HUB_TOKEN` is set AND the resolved `Host` is non-loopback | `Authorization: Bearer <token>` required → else `401` (constant-time compare). A remotely-reachable hub otherwise serves the whole code graph unauthenticated. Loopback reads stay open + byte-unchanged; mutations require the bearer regardless of host (TASK-487). |

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
| `src/core/web/routes/**`, `src/core/graph_os/**`, `src/core/thinking_os/**`, `src/core/board_os/**` (any code the hub imports **in-process**) | hub auto-reloads only with `--reload`; otherwise `cos hub restart` — staleness is detected by `cos hub status` / `cos doctor` (`hub.code_fresh`) and auto-bounced by `cos update` | same |
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

## Hub serves in-process core — staleness detection

The hub is one long-running process that imports `graph_os`, `web`,
`thinking_os`, and `board_os` **in-process** and serves the Graph tab +
`cos_*` endpoints for *every* registered project from those imports.
Python loads each module once at process start and never reloads a live
module, so a fix to core code (e.g. a `graph_os` edge-type validation
bug) only reaches consumers **after the hub restarts** — until then the
hub keeps serving the pre-fix code to all projects. This is the most
common "I fixed it but it's still broken" trap.

Three mechanisms close the gap so a consumer (a regular user, not the
meta-developer) never has to hunt for it:

- **`cos hub status`** prints a stale-code warning when the newest core
  `*.py` mtime is newer than the hub's start time (the `hub.pid` mtime,
  rewritten on every start/restart), naming `cos hub restart`.
- **`cos doctor`** surfaces the same signal as the `hub.code_fresh`
  check — WARN when stale, PASS when fresh or when no hub is running
  (never a false positive). The staleness predicate is the single SSOT
  helper `cli/hub_commands.py::_hub_code_is_stale()`, reused by status,
  doctor, and update.
- **`cos update`** auto-restarts a running, now-stale hub at the end of
  a non-dry-run, so the act of updating a project also makes the fresh
  core live for the Graph tab + tools.

Scope: only `*.py` the hub imports in-process counts (the helper walks
`cli/_resources.core_dir()`, skipping `tests/` and `__pycache__`). Hook
`.sh` files are live symlinks read per-invocation, not in-process, so
they are never part of this signal.

**Dev auto-reload** — `cos hub start --reload` runs uvicorn with
`reload=True` and `reload_dirs` scoped to `core_dir()` (not the whole
repo, which would storm on doc/test edits), so a meta-developer's core
edits go live with no manual restart. Reload mode drops a `hub.reload`
marker next to `hub.pid`; while it is present `_hub_code_is_stale()`
short-circuits to *fresh*, so `cos hub status` / `cos doctor` /
`cos update` never false-positive on a hub that already auto-reloads.
`cos hub restart` and the `cos update` auto-restart return the hub to
normal (non-reload) mode — reload is an explicit per-start dev opt-in,
not for a production/service hub.

## Symlink health

Every consumer project's `.claude/hooks/*.sh` /
`.codex/hooks/*.sh` is a symlink to `src/core/hooks/*.sh` in this meta repo.
Edits here reach every project **instantly** — no `cos update` needed.

If the meta repo is moved, those symlinks become dangling. Detect and
repair:

```bash
cos hub status                # summary line will say "Symlink health: broken in [...]"
cos sync-doctor               # per-project JSON report
cos sync-doctor --repair      # re-run install.sh on each broken project
```

Three resilience layers back this contract (TASK-346):

- **Passive nudge** — every `cos` invocation inside a consumer project
  probes the agent dirs for dangling symlinks (fail-open, one stderr
  line) and prints the `cos sync-doctor --repair` command when found.
- **`cos update` self-heal** — after re-linking, update prunes symlinks
  still dangling (obsolete targets from a moved/removed source) and
  warns on core-version drift (stamped `core-version.json` vs the
  installed core, same signal as `cos doctor`).
- **Install-mode-safe roots** — `cli/update.py` and `cli/sync_all.py`
  resolve the bundled core/adapters/templates trees via
  `cli/_resources.py` (importlib), not `Path(__file__)` hops, so they
  work under editable installs, wheels, and post-move reinstalls alike.

## Commands cheat-sheet

| Task | Command |
|---|---|
| Start the hub (first time) | `cos hub start` |
| Start with dev auto-reload (watches `core_dir`) | `cos hub start --reload` |
| Stop / restart | `cos hub stop` then `cos hub start` (or `cos hub restart`) |
| Status + meta repo + symlink health + code-staleness | `cos hub status` |
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
