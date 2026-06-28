---
id: TASK-595
title: "Delete or re-capture the orphan golden trees (claude_node-express, claude_vue-nuxt) \u2014 not in parity SECTIONS, stale in ~21 hooks"
swimlane: infra
kind: chore
epic: git-foundation-hardening
labels: [golden, tech-debt, code-review, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-26
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-595: Delete or re-capture the orphan golden trees (claude_node-express, claude_vue-nuxt) — not in parity SECTIONS, stale in ~21 hooks

**Outcome (one sentence):** Resolve the orphan golden trees surfaced by the ultra-review: tests/golden/claude_node-express and tests/golden/claude_vue-nuxt are git-tracked but absent from capture_golden.py + test_golden_parity.py SECTIONS (only base/django/nextjs × claude/codex are captured), so they silently diverge from src/core (currently ~21 hooks stale, incl. test-governor.sh). Either DELETE them (stack_lint only soft-warns on golden-section existence) or ADD them to SECTIONS so make golden-capture maintains them. Decide one and apply, so no contributor reads a stale golden as the rendered hook.</outcome>
<parameter name="repro">git diff each tests/golden/claude_{node-express,vue-nuxt}/.claude/hooks/*.sh against src/core/hooks/ — ~21 files diverge (LOCK_GRACE/pgrep in test-governor.sh, old cos-env/block-dangerous/session-context, etc.). test_golden_parity.SECTIONS (tests/test_golden_parity.py:32-39) covers only 6 sections; these two dirs are never scaffolded/byte-compared. cli/stack_lint.py ~line 111 checks only existence (soft warn), not content.

## Work Log
- 2026-06-28 [claude]: Chose re-capture over delete after verifying delete would break test_factory_lint_passes_with_golden (stack-lint…
