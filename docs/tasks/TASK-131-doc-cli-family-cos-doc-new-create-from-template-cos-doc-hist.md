---
id: TASK-131
title: "Doc CLI family \u2014 cos doc-new (create from template) + cos doc-history (git versions) + cos doc-lint single-file"
swimlane: cli
kind: feature
epic: doc-system
labels: [docs-system, cli, tooling, audit-d4-f1, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-131: Doc CLI family — cos doc-new (create from template) + cos doc-history (git versions) + cos doc-lint single-file

**Outcome (one sentence):** Three thin CLI surfaces so doc lifecycle is tool-driven not hand-copied: cos doc-new --layer L --path P scaffolds correct frontmatter+opening-block+nav from the template (D4-F1); cos doc-history <path> shells git log --follow + show to answer 'show me prior versions of this doc' (D4-F2); cos doc-lint <path> validates one doc via the existing docs-lint single-file arg (D4-F4). Reuse docs-lint.sh + templates; no new parsers.

## Read First
- src/cli/main.py
- src/core/scripts/docs-lint.sh
- docs/governance/_templates/doc-cheat-sheet.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a contributor needs to create, inspect the history of, or lint a single doc
- **When** they run `cos doc-new --layer engineering --path docs/engineering/x.md`, `cos doc-history <path>`, or `cos doc-lint <path>`
- **Then** doc-new writes a file carrying the canonical header + opening block + nav breadcrumb; doc-history prints the git revision list (and full diffs with --show); doc-lint runs docs-lint.sh in single-file mode and exits non-zero on lint errors — all three registered on the `cos` CLI, reusing docs-lint.sh with no new parser.

## Work Log
- 2026-06-06 [claude]: Added src/cli/doc_commands.py (doc-new scaffolds canonical header+opening-block+nav; doc-history wraps git log --follow
- 2026-06-06 [claude]: committed 27e94114: src/cli/doc_commands.py, src/cli/main.py
