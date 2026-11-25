---
id: TASK-1130
title: "fix(docs): cos doc-lint checks a whole project's links and frontmatter; a fresh scaffold lints clean"
swimlane: templates
kind: bug
epic: null
labels: [docs-update, governance, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-11-25
started: 2026-11-25
completed: null
agent_session: ses-claude-20261125-165238-7b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-1130: fix(docs): cos doc-lint checks a whole project's links and frontmatter; a fresh scaffold lints clean

**Outcome (one sentence):** A consumer runs `cos doc-lint` with no arguments and learns about every broken internal link, missing anchor and bad frontmatter in its project, and a fresh scaffold passes it.

## Read First
- src/core/scripts/audit_doc_links.py
- src/core/scripts/docs-lint.sh
- src/cli/doc_commands.py

## Repro Steps
cos init -a claude,codex -t fastapi -n probe --yes --no-register --no-git; cd probe; make docs-lint (exit 1: fastapi-rules.md has no frontmatter; no link check at all); cos doc-lint with no paths errors "Missing argument".

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh fastapi scaffold, **When** `cos doc-lint` runs with no arguments, **Then** it exits 0 with no broken link and no frontmatter error.
- **Given** a consumer doc that links to a file that is then deleted, **When** `cos doc-lint` runs, **Then** it exits non-zero and names the file and the dead link.
- **Given** coding-os itself, **When** `cos doc-lint` runs, **Then** it reports the same link findings as the old meta-only audit.

## Work Log
- 2026-11-25 [claude]: auditor moved to src/core/scripts with --root; cos doc-lint no-arg = links+headers; fastapi/go/python stack docs got…
- 2026-11-25 [claude]: commit 9eecff679f — fix(docs): cos doc-lint checks every link and header in a project; a fresh scaffold lints clean
- 2026-11-25 [claude]: green: test_cli+stack_rule 302, scaffold 177, verify-hooks, hooks_fail_closed+golden 32 (after golden-capture), make…
- 2026-11-25 [claude]: commit 30c431f792 — fix(docs): cos doc-lint finds the project root from any subfolder and never reads outside it
- 2026-11-25 [claude]: r1 rework green: lint, size, docs-lint, verify-hooks, golden 32, cli 302, scaffold 182 (+5 doc-lint AC tests), audit…
