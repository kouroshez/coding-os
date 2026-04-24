---
id: TASK-072
title: "Hub UI: Settings tab for feature flags, env vars, hub daemon controls, backend selection"
swimlane: core
kind: feature
epic: hub-tab-scaffold
labels: [hub, ui, settings, feature-flags]
status: icebox
priority: P2
appetite: "5h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-072: Hub UI — Settings tab

**Outcome (one sentence):** A single `/settings` tab exposes (and persists): graph backend selector (sqlite / kuzu), SSE poll interval, theme, the registered-projects list, hub daemon controls (start/stop/restart status), and the feature-flag toggles that gate Hooks / Roles / Metrics / Retrieval Feedback tabs — all persisted to `$COS_STATE_DIR/hub-config.json`.

## Read First

- [cli/hub_commands.py](../../cli/hub_commands.py) — existing `cos hub status / start / stop / logs / service install` flow.
- [docs/engineering/hub-architecture.md](../../docs/engineering/hub-architecture.md) — architecture contract; this task updates the "Settings" section.
- [core/web/server.py](../../core/web/server.py) — where the new `/api/hub/config` route registers.
- [core/web/ui/src/layout/AppShell.tsx](../../core/web/ui/src/layout/AppShell.tsx) — NAV constant; add Settings entry here.
- [adapters/claude/sdk_dispatcher.py](../../adapters/claude/sdk_dispatcher.py) — for the theme/agent-aware toggles preview.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the Hub running
  **When** the user navigates to `/settings`
  **Then** five sections render: **General** (theme, SSE poll ms with min/max clamp `[500, 30000]`), **Graph Backend** (sqlite | kuzu radio with a "current index size" info line each), **Projects** (table from the registry with `open`, `sync`, `doctor` action buttons), **Daemon** (current status + start/stop buttons that call the existing CLI endpoints, with a tail-log stream), **Feature Flags** (toggle per tab: `hooks.enabled`, `roles.enabled`, `metrics.enabled`, `retrieval.enabled`, `wiki.enabled`).
- **Given** any changed setting
  **When** the user clicks "Save"
  **Then** the change POSTs to `/api/hub/config`, the file `$COS_STATE_DIR/hub-config.json` is rewritten atomically (write-tmp-then-rename), and a success toast fires. AppShell re-reads flags via SSE `config-updated` event and shows/hides tabs without a page reload.
- **Given** an invalid value (e.g. negative poll interval, unknown backend)
  **When** the user hits Save
  **Then** the envelope returns `fail(validation, …)`, the offending field goes red with the error message inline, and the file is not modified.
- **Given** missing or corrupt `hub-config.json`
  **When** the page loads
  **Then** a banner offers "Reset to defaults"; defaults are the same baked constants the Hub already uses today so behaviour is unchanged.
- **Tests:** `tests/test_hub_config_endpoint.py` covers load/save/validate/atomic-rename; Playwright `e2e/hub-settings.spec.ts` covers the UI flow.

## Implementation Notes

1. **Config schema** (dataclass + Pydantic model): `HubConfig { theme: str, sse_poll_ms: int, graph_backend: Literal["sqlite","kuzu"], feature_flags: dict[str, bool] }`. Backward-compat: unknown keys preserved (round-trip).
2. **Atomic write:** `write_tmp + os.replace` — never a partial file.
3. **Feature flags** gate both the NAV entry (AppShell) and the route (so direct URL typing still gets a 404 fallback, not a blank page).
4. **Projects table** reuses the existing `cos registry list` output shape — do not re-implement registry access in the UI.
5. **SSE config broadcast:** add `ConfigChangeEvent` to the existing SSE stream; clients subscribed to `/api/stream/events` update the flag map.
6. **No backend-heavy settings on this page** — anything that requires a daemon restart to take effect is flagged with a yellow "Requires restart" pill and the save action also offers a "Restart daemon now" secondary button.

## Dependencies

- **Depends on:** nothing hard; benefits from TASK-071 (watchdog SSE) landing first for lower-latency config propagation.
- **Unblocks:** TASK-084/085/086/087 feature flags (all four expose their `*.enabled` flag here first, before shipping the tab).

## Work Log
