<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-25 -->
# Hub Architecture

Purpose: Canonical contract for the singleton hub daemon (FastAPI + React SPA on :9188), per-project routing via `/api/p/<slug>/*`, and the propagation matrix for live symlinks (hooks/rules/skills/commands).
Read when: editing `core/web/`, `cli/hub_*.py`, or any code that registers a project with the hub.

> Nav: [docs/](../) · [engineering/](./)

One uvicorn process, one browser tab, every coding-os project. This doc
explains where state lives, how changes propagate, and which port serves
what.

## Three address spaces

| Location | Holds | Mutated by |
|---|---|---|
| **Meta repo** `/Users/<you>/.../coding-os/` | `core/` + `adapters/` + `templates/` + `cli/` (source of truth) | humans + agents edit directly |
| **Hub state** `~/.coding-os/` | `registry.json`, `hub.pid`, `hub.log`, `groups/` | `cos registry`, `cos hub`, `cos graph-groups`, first-run bootstrap |
| **Project state** `<repo>/.coding-os/` | `thinking_os.db`, `.agent`, `<agent>/session-id`, `<agent>/sessions/*.json`, `.hooks.log`, `installed-manifest.json` | hooks, MCP server, `install.sh`, CLI commands run inside the project |

**`~/.coding-os/` does NOT hold code.** The hub loads every byte of
`core/` and `adapters/` directly from the meta repo — `uv tool install
--editable .` links the `cos` bin to the repo source. Moving or deleting
the repo breaks the hub; `~/.coding-os/` by itself is useless.

## Scrumban board API — live agents (`/api/board/list`)

Successful board list payloads include:

| Field | Meaning |
|---|---|
| `agent_states` | Per adapter id: `active` / `present` / `offline` (from `.coding-os/<agent>/sessions/*.json` written by `agent-presence.sh`, with DB fallback). |
| `agent_manifest` | Rows built from `adapters/*/adapter.yaml` (id, label, `hub_glyph`, `hub_color`, session prefix) plus a synthetic **`human`** row — no hardcoded adapter tuple in Python or React. |
| `presence_scope` | Today always `per_project`: presence files are read only under the **currently scoped project root** (the slug passed to `/api/p/<slug>/…` or `COS_PROJECT_ROOT`). |
| `cursor_model` | Optional display-only string: first line of `.coding-os/cursor/.model` when the file exists. **Not** used for green/red presence (runtime stays `COS_AGENT=cursor`). |

**Not implemented:** aggregating “this adapter is active in *any* registered repo” under `~/.coding-os/`. That would need a separate global store or a registry walk; the field `presence_scope` leaves room to extend the contract later.

## Ports

| Port | Service | Lifetime |
|---|---|---|
| **9188** | Hub FastAPI (uvicorn) — serves `/api/*` + SPA from `core/web/ui/dist/` | always, singleton per user |
| **5173** | Vite dev server (HMR) — edit-save-see-in-browser loop | only when `make ui-dev` is running |

5173 **proxies** `/api` and `/health` to 9188, so the backend stays
single-homed. No conflict between the two — they serve different
purposes and you rarely run both at once.

## Propagation matrix — edit X, how does it reach consumer projects?

| Change | Propagates to the meta repo itself | Propagates to consumer projects |
|---|---|---|
| `core/hooks/*.sh`, `core/rules/**`, `core/skills/**`, `core/commands/**` | instantly (symlinked by `install.sh`) | instantly (same symlinks in every project) |
| `core/hooks/registry.yaml` | `make sync` (re-renders `adapters/*/[settings\|hooks].template.json`) | `cos sync-all` (calls each adapter's `install.sh` per project) |
| `adapters/<agent>/adapter.yaml` field | `make sync` | `cos sync-all` |
| `core/thinking_os/db.py` schema (new migration) | next `cos`/`hub` invocation runs `init_db` | `cos sync-all` forces `init_db` on every project's DB |
| `core/web/ui/src/**` (SPA source) | `make ui-build` → `dist/` → hub serves new bundle on next request (hard-refresh browser) | same — all projects share one SPA bundle served by the hub |
| `core/web/routes/**` (FastAPI) | hub daemon auto-reloads if started with `--reload`, otherwise `cos hub stop && cos hub start` | same |
| `cli/**` | `uv tool install --editable .` pointed at this repo, so next `cos` invocation picks it up | same |

## "I edited the UI, why don't I see it?"

Three things must line up:

1. **Build** — `core/web/ui/src/` is TypeScript source. The browser sees
   `core/web/ui/dist/`. Run `make ui-build` (≈3s) OR keep `make ui-dev`
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
`.codex/hooks/*.sh` is a symlink to `core/hooks/*.sh` in this meta repo.
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

The result: you edit `core/**`, every registered project sees it via
symlink or `cos sync-all`; you edit `core/web/ui/**`, one SPA build
updates every project's panel. No fanned-out `.coding-os/` copies to
keep in sync.
