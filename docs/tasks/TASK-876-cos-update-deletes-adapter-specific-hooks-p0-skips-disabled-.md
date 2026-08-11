---
id: TASK-876
title: "cos update deletes adapter-specific hooks (P0) + skips disabled_skills/module filters and settings re-render (P1)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-876: cos update deletes adapter-specific hooks (P0) + skips disabled_skills/module filters and settings re-render (P1)

## Outcome
`cos update` no longer deletes adapter-specific hooks, honors `disabled_skills`/module-disabled rules, skips the two catalog rules install.sh deliberately excludes, and re-registers hooks in the agent settings file. Verified by A/B on a real consumer project.

## Read First
- src/cli/_update_manifest.py (`_build_target_assets`, `_disabled_skills`, `_module_disabled_assets`)
- src/cli/update.py (`_sync_hook_registration`)
- src/core/scripts/install-adapter.sh (disabled-skill sweep :182-232; non-active rules :148-172)

## Repro Steps
1. `cos init -a claude -t python -n consumer -y` in a scratch dir, then `cos update --dry-run` — clean.
2. `cos skill disable a11y`, then `cos update --dry-run`.
   Expected: no changes. Actual (pre-fix): `Added skills: a11y` — the next update relinks it, undoing the opt-out.
3. Remove two `hooks.PreToolUse` groups from `.claude/settings.json`, then `cos update`.
   Expected: registration restored. Actual (pre-fix): "already up to date" while those safety hooks never fire.

## Acceptance
- **Given** a project with claude+codex adapters, **When** `cos update` runs, **Then** codex-*-dispatch.sh and agent-memory hooks survive and newly shipped adapter hooks are added.
- **Given** `.coding-os.yaml::disabled_skills` entries, **When** `cos update` runs, **Then** disabled skills/rules stay unlinked.
- **Given** the install.sh exclusion of dimension-registry.md/skill-enforcement.md, **When** `cos update` runs, **Then** they are not re-linked.
- **Given** a settings file behind the shipped template, **When** `cos update` runs, **Then** the `hooks` key is re-rendered and every other key is preserved.

## Notes
Secondary items deliberately NOT in scope (each is its own change, none blocks this card): wheel omits core/scripts/extract_disabled_*.py; per-agent manifest overwrite; dead `--yes` flag; site-packages/src legacy paths in 14 CLI files.

## Work Log
- 2026-08-04 [claude]: P0 CONFIRMED by execution on a fresh consumer project (TASK-884 review): cos init → doctor 59 PASS/0 FAIL; then cos…
- 2026-08-07 [claude]: P0 half FIXED (97e19e9b): _build_target_assets enumerated only src/core/hooks, so every adapter-owned hook looked…
- 2026-08-09 [claude]: SHA correction: the P0 fix is 54dac1d7 "fix(cli): stop cos update deleting adapter-owned hooks" — the earlier-cited…
- 2026-08-09 [claude]: Scope now P1-only: the P0 adapter-hook deletion is fixed and on main (54dac1d7). Remaining: _build_target_assets…
- 2026-08-11 [claude]: P1 closed: disabled_skills filter + hook re-registration, both proven by A/B on a real consumer project.
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
