---
id: TASK-1092
title: "fix(scripts): auto-regen-doc-index overwrites a hand-written 00-index.md that has no auto-index fence"
swimlane: docs
kind: bug
epic: null
labels: [ready]
status: testing
priority: P1
appetite: 2h
created: 2026-11-23
started: 2026-11-23
completed: null
agent_session: ses-claude-20261107-135839-5342
depends_on: []
blocked_by: []
references: []
---
# TASK-1092: fix(scripts): auto-regen-doc-index overwrites a hand-written 00-index.md that has no auto-index fence

**Outcome (one sentence):** regen_doc_index.py never rewrites an existing 00-index.md that lacks the BEGIN/END auto-index fence; it skips it untouched.

## Read First
- docs/engineering/section-index.md
- src/scripts/regen_doc_index.py

## Repro Steps
1. `cos init -t brand-design` (or any project whose `docs/00-index.md` / `docs/playbooks/00-index.md` has no `<!-- BEGIN/END auto-index -->` fence).
2. Edit `docs/brand.md`; the PostToolUse `auto-regen-doc-index` hook runs `regen_doc_index.py docs/`.
Expected: the hand-written `docs/00-index.md` is left untouched.
Actual: `_splice_into_existing` returns the bare auto block, the whole index is replaced by ~7 lines, and `make docs-lint` fails on the missing front-matter header.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an existing `00-index.md` without the auto-index fence, **When** `regenerate()` runs for its directory, **Then** the file is byte-identical afterwards and the call reports a skip (returns None)
- **Given** an index with the fence, **When** `regenerate()` runs, **Then** only the fenced block changes (existing behaviour)
- **Given** the regen and script-entrypoint suites plus `make lint`, **When** run, **Then** they pass

## Work Log
- 2026-11-23T08:40:00Z — Fix: regenerate() skips an existing 00-index.md without the auto-index fence (SKIP line, no write); the stack's hand-written indexes keep no fence so brand.md is not listed twice. Verified: regen suite 10 passed (new no-fence test + self-reference fixture fenced), script entrypoints + size gate 48 passed, make lint, docs-lint, scratch brand-design docs/ and playbooks/ indexes byte-identical after a regen run.
