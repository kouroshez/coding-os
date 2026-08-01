---
id: TASK-756
title: "Claude adapter: dual auth mode (subscription OAuth / API key) selectable in Hub panel"
swimlane: adapters
kind: feature
epic: null
labels: [claude-sdk, hub, auth, settings, ready]
status: archive
priority: P1
appetite: 3h
created: 2026-07-01
started: 2026-07-01
completed: 2026-07-01
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-756: Claude adapter: dual auth mode (subscription OAuth / API key) selectable in Hub panel

**Outcome (one sentence):** Hub Settings panel exposes a Claude Auth section (Subscription/OAuth vs API Key, mutually exclusive, masked-secret storage) that deterministically switches every Claude dispatch (chat + formula) between the CLI's own OAuth session and a user-supplied ANTHROPIC_API_KEY, so subscription-based users (the common case) and API-key users are both first-class, switchable without restarting the Hub.

## Read First
- src/core/web/routes/settings.py
- src/adapters/claude/sdk_dispatcher.py
- src/core/web/ui/src/pages/SettingsPage.tsx
- src/core/web/routes/cognition.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** hub-settings.json has no claude_auth section, **When** GET /api/settings runs, **Then** it returns claude_auth.mode="subscription" with api_key_set=false (byte-identical dispatch behavior to today — the default must be a no-op).
- **Given** the user PATCHes claude_auth to {mode:"api_key", api_key:"sk-ant-..."}, **When** the Hub dispatches a chat or formula session, **Then** ClaudeAgentOptions.env carries ANTHROPIC_API_KEY=<key> (verified via platform.claude.com/docs/en/authentication precedence: API key beats subscription OAuth in non-interactive/SDK mode) and the response never echoes the raw key back — GET returns only api_key_set + a masked last-4 preview.
- **Given** mode is "subscription" (default or explicitly reverted), **When** dispatch options are built, **Then** ANTHROPIC_API_KEY is explicitly cleared in the subprocess env (not just omitted) so a stray key in the Hub server's own shell environment cannot silently override the user's chosen mode.
- **Given** the Settings PATCH payload omits the api_key field entirely, **When** the section is saved, **Then** the previously stored key is preserved untouched (exclude_unset semantics — never require re-entering the key just to flip mode or edit an unrelated section).

## Work Log
- 2026-07-01 [claude]: Edit settings.py
- 2026-07-01 [claude]: Edit settings.py
- 2026-07-01 [claude]: Edit settings.py
- 2026-07-01 [claude]: Edit settings.py
- 2026-07-01 [claude]: Edit settings.py
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit sdk_dispatcher.py
- 2026-07-01 [claude]: Edit session-options-builder.md
- 2026-07-01 [claude]: Edit session-options-builder.md
- 2026-07-01 [claude]: Edit claude-sdk.md
- 2026-07-01 [claude]: Edit claude-sdk.md
- 2026-07-01 [claude]: Edit test_session_options_parity.py
- 2026-07-01 [claude]: Edit test_session_options_parity.py
- 2026-07-01 [claude]: Edit test_session_options_parity.py
- 2026-07-01 [claude]: Edit test_hub_settings_claude_auth.py
- 2026-07-01 [claude]: Edit SettingsPage.tsx
- 2026-07-01 [claude]: Edit SettingsPage.tsx
- 2026-07-01 [claude]: Edit SettingsPage.tsx
- 2026-07-01 [claude]: Edit SettingsPage.tsx
- 2026-07-01 [claude]: Edit SettingsPage.tsx
- 2026-07-01 [claude]: Edit SettingsPage.tsx
- 2026-07-01 [claude]: committed 77437972 · 7 files
- 2026-07-01 [claude]: commit ecba79cca7 — chore(hub-ui): regenerate api-types.ts (claude_auth schema + 2.5wk of route drift)
- 2026-07-01 [claude]: Implemented via _claude_auth_env(cwd) in sdk_dispatcher.py — self-contained, reads hub-settings.json::claude_auth,…
- 2026-07-01 [claude]: commit a78249fb81 — chore(board): sync TASK-756 (dual Claude auth mode) to testing
