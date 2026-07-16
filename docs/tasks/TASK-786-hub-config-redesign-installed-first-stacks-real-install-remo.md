---
id: TASK-786
title: "Hub Config redesign: installed-first stacks + real install/remove, active-skills grouped-by-stack, adapters add/remove, allow-listed MCP add/remove, grouped read-only hooks, kernel-badge polish, Marketplace top-nav (EM coming-soon)"
swimlane: core
kind: feature
epic: hub-config-modernization
labels: [hub, config, ui, extension-manager, cli, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260703-211955-5bf7
depends_on: []
blocked_by: []
references: []
---
# TASK-786: Hub Config redesign: installed-first stacks + real install/remove, active-skills grouped-by-stack, adapters add/remove, allow-listed MCP add/remove, grouped read-only hooks, kernel-badge polish, Marketplace top-nav (EM coming-soon)

---
id: TASK-786
title: "Hub Config redesign: installed-first stacks + real install/remove, active-skills grouped-by-stack, adapters add/remove, allow-listed MCP add/remove, grouped read-only hooks, kernel-badge polish, Marketplace top-nav (EM coming-soon)"
swimlane: core
kind: feature
epic: hub-config-modernization
labels: [hub, config, ui, extension-manager, cli, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-786: Hub Config redesign (installed-first stacks, active-skills grouped-by-stack, adapters add/remove, allow-listed MCP, grouped hooks, kernel badge, Marketplace EM stub)

**Outcome (one sentence):** The per-project Hub Config surface becomes modern/enterprise + principled: Stacks shows only INSTALLED stacks with a +Add picker (real cos add-stack / remove-stack, meta-repo guarded); Skills shows only ACTIVE skills grouped by originating stack with provenance and clean toggles (existing set_project_skill); Adapters gains real add (cos add-adapter) + safe remove (never the last); MCP redesigned with +Add limited to a first-party allow-list (honoring extension-manager.md invariants) + remove, meta-guarded; Hooks kept read-only but grouped by category, collapsible; the kernel-locked module badge is redesigned; a Marketplace top-nav tab lands as an Extension-Manager coming-soon surface. Card-based, token-driven, a11y-clean.

## Read First
- docs/engineering/extension-manager.md
- src/core/web/routes/config.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/cli/add_stack.py
- src/cli/remove_stack.py
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** a consumer project on the Stacks tab **When** it loads **Then** only installed stacks are primary and a +Add control reveals the not-installed ones; install/remove round-trips through cos add-stack/remove-stack and refreshes; on the coding-os meta-repo mutation is guarded with a clear caution.

**Given** the Skills tab **When** it loads **Then** only active (enabled/extra) skills show, grouped under their originating stack, each marked stack-provided vs user/community, with a clean enable/disable/remove wired to the existing PATCH.

**Given** the Adapters tab **When** a runnable adapter is present **Then** it can be added (cos add-adapter) and removed (guarded so the last adapter can never be removed); MCP +Add adds only first-party allow-listed servers (custom/URL/upload deferred to the Extension Manager) writing to the adapter config, removable, both meta-guarded; Hooks render grouped-by-category, collapsible, read-only; the kernel module row uses a distinct polished locked treatment; the primary header has a Marketplace tab routing to an Extension-Manager coming-soon page; AND make ui-build + ConfigPage vitest + tests/test_config_routes.py + python server --test all pass.

## Work Log
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit test_config_routes.py
- 2026-07-04 [claude]: Edit test_config_routes.py
- 2026-07-04 [claude]: commit 636e4167ac — feat(hub): config stack/adapter/MCP install-remove endpoints (meta-guarded)
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit test_config_routes.py
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.test.tsx
- 2026-07-04 [claude]: Edit ConfigPage.test.tsx
- 2026-07-04 [claude]: Edit ConfigPage.test.tsx
- 2026-07-04 [claude]: commit 0c4c0fc92f — feat(hub): redesign Config tabs — installed-first stacks, grouped skills, adapter/MCP add-remove
- 2026-07-04 [claude]: Edit MarketplacePage.tsx
- 2026-07-04 [claude]: Edit AppShell.tsx
- 2026-07-04 [claude]: Edit AppShell.tsx
- 2026-07-04 [claude]: Edit App.tsx
- 2026-07-04 [claude]: Edit App.tsx
- 2026-07-04 [claude]: Edit App.tsx
- 2026-07-04 [claude]: Edit MarketplacePage.test.tsx
- 2026-07-04 [claude]: Deliberation: MCP-add scoped to a first-party allow-list (not arbitrary command→.mcp.json) because installing an MCP…
- 2026-07-04 [claude]: Done + verified: config.py mutation endpoints (stacks/adapters/mcp, meta-guarded, audited) + skills stack-membership…
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit test_config_routes.py
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: commit 1012152d61 — fix(hub): review fixes for config mutations — cos JSON parse, argv guard, cwd shadow
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit config.py
- 2026-07-04 [claude]: Edit test_config_routes.py
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: Edit ConfigPage.tsx
- 2026-07-04 [claude]: commit b9734377b5 — fix(hub): allow config mutations on coding-os; mark only active skills on; kernel badge nowrap
- 2026-07-04 [claude]: User-feedback fixes: (1) removed the meta-repo mutation guard so +Add/remove for stacks/MCP/adapters work on…
