---
id: TASK-127
title: "Gate the doc header contract — docs-lint strict on changed docs in CI + pre-commit batch + freeform-create WARN hook"
swimlane: core
kind: feature
epic: doc-system
labels: [docs-system, enforcement, ssot, audit-d5-f1, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-127: Gate the doc header contract — docs-lint strict on changed docs in CI + pre-commit batch + freeform-create WARN hook

**Outcome (one sentence):** The header+taxonomy contract docs-system.md advertises is actually enforced where docs are produced: (1) CI runs docs-lint in strict mode on git-changed docs only (D5-F1), (2) the git pre-commit batch gains a doc-header check for changed docs/**/*.md (D5-F7), (3) a PreToolUse Write WARN fires when a new freeform doc lacks a valid header, pointing at doc-cheat-sheet (D5-F4). Legacy backlog stays advisory; only new/changed docs gate.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/scripts/docs-lint.sh
- src/core/hooks/_helpers/pre_commit_batch.py
- src/core/hooks/enforce-template.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** docs-system.md advertises the SSOT header+taxonomy contract but docs-lint enforces it advisory-on-all-docs only (legacy backlog would break a hard gate).
- **When** docs-lint.sh gains a `--changed` mode (lints only the git-changed `docs/**/*.md`), CI runs it under `COS_DOCS_LINT_STRICT=1`, the git pre-commit batch warns on changed `docs/**/*.md` with a bad header, and a PreToolUse Write hook warns when a NEW freeform `docs/*.md` lacks the header.
- **Then** new/changed docs are held to the full header contract (strict in CI, WARN at commit + write time) while the pre-existing backlog stays advisory — verified by `docs-lint.sh --changed` exiting nonzero under strict on a malformed new doc and zero when the header is valid.

## Work Log
- 2026-06-07 [claude]: Shipped 3 additive WARN/gate surfaces for the doc-header contract (reusing docs-lint Check-1, no new lint logic): (a) do
- 2026-06-07 [claude]: committed 12e875ce: .github/workflows/ci.yml, src/core/hooks/_helpers/pre_commit_batch.py, src/core/hooks/enforce-templa
