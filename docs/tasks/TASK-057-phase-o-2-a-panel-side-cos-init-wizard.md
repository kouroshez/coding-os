---
id: TASK-057
title: "Phase O.2.a — Panel-side cos init wizard"
swimlane: core
kind: feature
epic: phase-o
labels: [hub, ui, scaffold]
status: icebox
priority: P2
appetite: "2d"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-057: Phase O.2.a — Panel-side cos init wizard

**Outcome (one sentence):** Users can create a brand-new coding-os project from http://127.0.0.1:9188 without dropping to a terminal.

## Read First
- [cli/main.py](../../cli/main.py) — `init` click command (signature + idempotent resume path)
- [cli/adapter_registry.py](../../cli/adapter_registry.py) and [cli/stack_registry.py](../../cli/stack_registry.py) — list sources for the dropdowns
- [core/web/routes/hub.py](../../core/web/routes/hub.py) — where the new endpoint lands; reuse `_validate_project_path` pattern
- [core/web/ui/src/pages/HubHome.tsx](../../core/web/ui/src/pages/HubHome.tsx) — `ImportDialog` is the UX template for a new `NewProjectDialog`

## Deliverables
1. **Backend:** `GET /api/hub/stacks` + `GET /api/hub/adapters` in `hub.py` — return `{id, label}[]` from `load_stack_registry(TEMPLATES_DIR)` / `load_adapter_registry(ADAPTERS_DIR)`. No literal names.
2. **Backend:** `POST /api/hub/init {path, stack, agent, slug?}` in `hub.py` — must:
   - validate `path` (absolute, parent exists, writable, not already a cos project unless `overwrite=false` → error)
   - spawn `subprocess.Popen([cos_bin, "init", "--path", path, "--stack", s, "--agent", a, "--slug", slug], ...)` with 120s timeout, capture stdout/stderr
   - stream progress via SSE at `/api/hub/init/stream/{job_id}` (line-per-event) OR return `{job_id}` + polling endpoint `GET /api/hub/init/{job_id}` — pick whichever is simpler to test
   - on success: call `cli.registry.add_project(path)` then return the fresh entry
3. **CLI:** `cos init` MUST accept `--path PATH` (default cwd) so the API can delegate. Audit current signature; add if missing.
4. **Frontend:** `NewProjectDialog` beside `ImportDialog` in `HubHome.tsx`: inputs = path + stack dropdown + agent dropdown + slug (optional) + submit. Poll/stream progress; disable resubmit while busy.
5. **Tests:** `tests/test_hub_init_endpoint.py` — happy path (tmp_path), validation rejects (non-writable, exists but not empty, bad stack), subprocess timeout surface as `{category: "transient"}`.

## Acceptance (G/W/T)
- **Given** an empty directory at `/tmp/my-new-app` and the Hub running
- **When** the user fills `NewProjectDialog` (path=`/tmp/my-new-app`, stack=`nextjs`, agent=`claude`, slug=`my-new-app`) and submits
- **Then** within 60s the card appears on HubHome with `source: "registry"`, `/tmp/my-new-app/.coding-os/` exists, `/tmp/my-new-app/AGENTS.md` exists, and clicking Board opens `/p/my-new-app/board` with an empty Scrumban grid.

## Verification
- `uv run --extra rag pytest tests/test_hub_init_endpoint.py -q`
- `uv run --extra rag pytest tests/test_hub_registry_crud.py tests/test_cli_init_flags.py -q` (no regression)
- SPA: `cd core/web/ui && npm run build` (TS exhaustive check must stay green)
- Manual: in browser create a project into `$(mktemp -d)`, confirm it opens and board loads.

## Non-goals
- No scaffolding templates beyond the existing `TEMPLATES_DIR` — don't add new stacks in this task.
- No remote file-system picker; text input + suggest-roots chips is enough.
- No multi-user auth — localhost-only invariant holds.

## Work Log
