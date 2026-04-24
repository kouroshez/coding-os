---
id: TASK-061
title: "Phase O.2.d — Harden middleware + frontend against cross-project scope leaks"
swimlane: core
kind: bug
epic: phase-o
labels: [hub, scope, cache, regression-guard]
status: icebox
priority: P1
appetite: "4h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---
# TASK-061: Phase O.2.d — Harden middleware + frontend against cross-project scope leaks

**Outcome (one sentence):** Adding a new React Query hook or SSE-style stream cannot silently reuse the previously-opened project's payload when the user switches projects.

## Read First
- [core/web/ui/src/lib/hooks.ts](../../core/web/ui/src/lib/hooks.ts) — `useApiGet` already includes `scope` in queryKey
- [core/web/ui/src/features/cos-board/useBoardStream.ts](../../core/web/ui/src/features/cos-board/useBoardStream.ts) — precedent: SSE + history effects keyed on `pathname`
- [core/web/ui/src/lib/api-client.ts](../../core/web/ui/src/lib/api-client.ts) — `rewriteForProjectScope`
- [core/web/_project_context.py](../../core/web/_project_context.py) — `ProjectScopeMiddleware`

## Context
The Phase O.1 fix put `scope` into `useApiGet`'s queryKey and made `useBoardStream` re-key on `pathname`. This task institutionalises that fix so future features inherit it by default.

## Deliverables
1. **New hook `useProjectScope()`** in `core/web/ui/src/lib/scope.ts` that returns `{slug: string | null, isHub: boolean}` derived from `useLocation()`. Replace the ad-hoc regex in `useApiGet`/`AppShell`/`ProjectSwitcher`/`useBoardStream` with this single hook.
2. **Global scope-change invalidation** in `core/web/ui/src/main.tsx`: subscribe `QueryClient` to a custom event emitted when `useProjectScope`'s slug changes; `queryClient.removeQueries({queryKey: ['cos-scope']})` on change. Belt-and-braces so a leaked fetch in new code can't outlive the navigation.
3. **Lint rule / test `tests/test_ui_scope_discipline.py`** that scans `.ts`/`.tsx` under `core/web/ui/src/` and fails when:
   - A file matches `new EventSource(` without a neighbouring `useLocation()` or `useProjectScope()` import in the same module
   - A file matches `await apiGet\(` or `await apiPost\(` inside a `useEffect` whose dep array doesn't contain `pathname` or `scope`
   - Allowlist via a top-of-file `/* scope-ok: <reason> */` marker for global (`/api/hub/*`) endpoints; allowlist must be reviewed in the diff, not silently opted into
4. **Backend contract test `tests/test_scope_leak_contract.py`**:
   - Fire `/api/p/A/board/list` and `/api/p/B/board/list` in parallel `asyncio.gather` loops under the test ASGI client with different tmp DBs; assert payloads never cross over even under 50 interleaved requests
   - Covers the `ContextVar` + anyio `start_soon` contract already relied on; regression-guards the middleware

## Acceptance (G/W/T)
- **Given** `CosBoardPage` on `/p/A/board` with 10 tasks cached
- **When** the user clicks `B` in the ProjectSwitcher
- **Then** the board shows B's data within 2s, the Agent Stream panel contains only B's transitions, and the browser Network tab shows no request targeting `/api/p/A/` after navigation.

## Verification
- `uv run pytest tests/test_ui_scope_discipline.py tests/test_scope_leak_contract.py -q`
- `cd core/web/ui && npm run build` (ensure no new call sites regress the lint rule)
- Manual: two browser tabs on `/p/A/board` and `/p/B/board`; trigger a `cos task-move` in each project; each tab's stream panel shows only its own transition.

## Non-goals
- No rewrite of the existing `ProjectScopeMiddleware` — it works; this task is the regression guard, not a refactor.
- No server-side websocket fan-out — per-connection SSE is sufficient under the single-user localhost assumption.

## Work Log
