---
id: TASK-084
title: "Hub UI: Hooks tab — live viewer for PreToolUse/PostToolUse activity + registry explorer"
swimlane: core
kind: feature
epic: hub-tab-scaffold
labels: [hub, ui, hooks, observability]
status: icebox
priority: P2
appetite: "4h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-072]
blocked_by: []
references: []
---

# TASK-084: Hub UI — Hooks tab

**Outcome (one sentence):** Operators open `/hooks` in the Hub and see (a) a **live tailing feed** of `$COS_HOOK_LOG` with filters for agent / category / phase and (b) a **browsable registry explorer** of `core/hooks/registry.yaml` that shows, per hook, the `{event, matcher, agents}` coverage and the most recent fire timestamp.

## Read First

- [core/hooks/registry.yaml](../../core/hooks/registry.yaml) — SSOT of every hook (the tree the explorer renders).
- [core/hooks/cos-env.sh](../../core/hooks/cos-env.sh) — defines `COS_HOOK_LOG` path + NDJSON line format.
- [cli/main.py](../../cli/main.py) — `cos hooks-log` / `cos hooks-list` implementation; reuse the filter logic.
- [docs/engineering/hooks-reference.md](../../docs/engineering/hooks-reference.md) — user-facing reference.
- [core/web/routes/](../../core/web/routes/) — add a `hooks.py` route module alongside `board.py` / `graph.py`.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the Hooks tab is opened while any agent is active
  **When** a hook fires (SessionStart, PreToolUse, PostToolUse, etc.)
  **Then** a new row appears at the top of the feed within 250 ms, showing: timestamp, agent, phase badge (PRE / POST / EVENT), hook name, duration ms, and exit code. The log streams via SSE so no manual refresh.
- **Given** the registry explorer panel
  **When** the user expands a hook
  **Then** it shows the `registry.yaml` block (matcher, event, which agents it applies to per `hook_capabilities`), the raw script path, and the last fire timestamp (looked up by name from the tail of `$COS_HOOK_LOG`).
- **Given** filter controls
  **When** the user selects `agent=claude` + `phase=POST` + `category=graph`
  **Then** both the live feed and the historical tail filter accordingly; filter state persists in URL query string for deep-linking.
- **Given** a failing hook (exit code ≠ 0 or stderr present)
  **When** it appears in the feed
  **Then** the row renders with an amber left-border and a tooltip showing stderr; a click opens a full-height drawer with the full NDJSON payload pretty-printed.
- **Tests:** `tests/test_hooks_endpoint.py` (pagination + filtering), `e2e/hooks-live.spec.ts` (live-append asserts, filter URL round-trip).

## Implementation Notes

1. **Backend:** new route module `core/web/routes/hooks.py` exposing:
   - `GET /api/p/<slug>/hooks/registry` → parsed `registry.yaml` + capability matrix.
   - `GET /api/p/<slug>/hooks/log?limit=200&cursor=…&filters…` → paginated tail of `$COS_HOOK_LOG`.
   - SSE channel on the existing `/api/stream/events` emits `hook-fired` messages via a file-watch on `$COS_HOOK_LOG` (watchdog, not polling — aligns with TASK-071).
2. **UI:** `features/hooks/HooksPage.tsx` with `<HooksFeed>` (right column, virtualised list for 10k+ rows) + `<HooksRegistryTree>` (left column). Design tokens `--board` / `--ink` / `--accent` only — no hardcoded hex.
3. **Privacy/secrets:** pre-render scrubs lines matching `(token|secret|key|password)` with `***` — do not ship raw secrets even if they somehow leaked into a hook payload.
4. Tab feature-flagged by `hub-config.json::hooks.enabled` (set in TASK-072).
5. Replace the existing untracked `hub-*.png` Playwright screenshots from the prior session with real E2E screenshots committed under `tests/e2e/__screenshots__/hooks/`.

## Dependencies

- **Depends on:** TASK-072 (feature flag system). Soft-deps on TASK-071 (watchdog SSE) for truly live streaming; poll fallback works otherwise.
- **Unblocks:** nothing directly but is the cheapest of the 4 new tabs — a natural first slice of the hub-tab-scaffold epic.

## Work Log
