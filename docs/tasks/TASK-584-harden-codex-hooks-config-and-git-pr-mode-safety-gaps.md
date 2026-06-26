---
id: TASK-584
title: "Harden Codex hooks config and Git PR-mode safety gaps"
swimlane: adapters
kind: bug
epic: null
labels: [codex, mcp, hooks, git, hub, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-26
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-584: Harden Codex hooks config and Git PR-mode safety gaps

**Outcome (one sentence):** Codex starts without deprecated hook/config warnings, Git protected branch globs match UI semantics, Hub status detects unmanaged listeners, and Git PR-mode docs/UI disclose actual enforcement limits.

## Read First
- CLAUDE.md
- docs/playbooks/pr-workflow.md
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md
- docs/engineering/adapter-parity.md
- src/core/rules/git-workflow.md
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/hooks/branch-guard.sh
- src/cli/pr_commands.py

## Repro Steps
1. Start Codex in the coding-os repo and observe `[features].codex_hooks is deprecated`.
2. Observe hookify plugin hooks warning: unknown field `description`, expected `hooks`.
3. Run branch-guard with `COS_GIT_PROTECTED_BRANCHES='release/*'` and `git push origin release/v1`; it currently passes.
4. Run `cos hub status` while PID 87652 listens on 127.0.0.1:9188 without hub.pid; status says not running and start collides.
5. Compare `docs/playbooks/pr-workflow.md` git-state disabled behavior with `ConfigPage.tsx` always-probe behavior.
6. Review Config Git tab/docs for Codex hook boundary and GitHub-only remote rung clarity.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Codex reads config layers, **When** it starts in this project, **Then** local config uses `[features].hooks`, not deprecated `codex_hooks`.
- **Given** hookify plugin hooks are enabled, **When** Codex parses plugin hooks, **Then** `hooks/hooks.json` has a valid top-level schema without `description`.
- **Given** `COS_GIT_PROTECTED_BRANCHES='release/*'`, **When** an agent attempts `git push origin release/v1`, **Then** branch-guard blocks it with a protected-branch reason.
- **Given** a process is listening on the Hub port without a matching `hub.pid`, **When** `cos hub status` runs, **Then** it reports an unmanaged listener instead of `not running`.
- **Given** PR mode is disabled, **When** the Config Git tab opens, **Then** docs and UI agree that capability probing still runs before enablement.
- **Given** a Codex user configures PR mode, **When** they read the UI/docs, **Then** edit-isolation limits and GitHub-only remote rungs are explicit.

## Work Log
- 2026-06-26 [claude]: Created and started task after Firecrawl research confirmed `features.hooks` is canonical and `codex_hooks` is deprecated.
- 2026-06-26 [claude]: Migrated Codex configs to canonical features.hooks and removed hookify's invalid top-level description.
- 2026-06-26 [claude]: Added protected branch pattern matching so release/* blocks release/v1 push and ref rewrites.
- 2026-06-26 [claude]: Added unmanaged Hub listener detection in status/start and clarified Git tab guard limits.
- 2026-06-26 [claude]: Verification passed: adapter, hooks, CLI, UI, docs, golden parity, Codex config, hookify JSON.
- 2026-06-26 [claude]: Status transitioned to complete via cos task-done.
