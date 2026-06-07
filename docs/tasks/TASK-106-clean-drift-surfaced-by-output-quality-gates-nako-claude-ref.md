---
id: TASK-106
title: "Clean drift surfaced by output-quality gates: nako_/.claude refs, codex dispatcher drift, scaffold_manifest staleness, malformed frontmatter"
swimlane: infra
kind: chore
epic: null
labels: [tech-debt, drift, golden, follow-up-TASK-100, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-106: Clean drift surfaced by output-quality gates: nako_/.claude refs, codex dispatcher drift, scaffold_manifest staleness, malformed frontmatter

**Outcome (one sentence):** Rescoped after triage — only the Batch-7 dead-stub removal is actionable: delete the two no-op MERGED stub hooks (verify-changed-file.sh + doc-sync-reminder.sh) from registry + cursor dispatcher + tests, then regen adapter templates & golden. The other 4 surfaced items are non-actionable (wrong premise / deferred / other-epic) and are documented in the Work Log rather than fixed.

## Work Log
- 2026-06-07 [claude]: Batch-7 done: deleted dead no-op stubs verify-changed-file.sh + doc-sync-reminder.sh (MERGED into enforce-doc-sync.sh) f
- 2026-06-07 [claude]: committed 10fb07e4: src/adapters/claude/settings.template.json, src/adapters/cursor/adapter.yaml, src/adapters/cursor/ho
