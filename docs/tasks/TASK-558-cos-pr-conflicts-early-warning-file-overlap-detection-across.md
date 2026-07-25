---
id: TASK-558
title: "cos pr conflicts: early-warning file-overlap detection across concurrent agent branches (multi-agent at scale)"
swimlane: cli
kind: feature
epic: pr-mode-hardening
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-558: cos pr conflicts: early-warning file-overlap detection across concurrent agent branches (multi-agent at scale)

**Outcome (one sentence):** 5+ agents on one repo get an early, read-only warning when their branch edits files a live peer branch also edits — the pre-land layer the merge-queue (late, post-CI) doesn't provide. A new `cos pr conflicts` computes each agent branch's touched files (merge-base..branch committed diff + that worktree's uncommitted porcelain) and reports cross-branch overlap. Advisory only (exit 0, never blocks; legitimate co-editing is allowed). Frozen-base-snapshot is deliberately NOT built — rebase-at-submit + merge-base already handle base drift, so a separate snapshot store would be speculation.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md
- src/core/skills/pr-mode-driver/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** two live agent branches agents/a/s1 and agents/b/s2 that both changed foo.py, **When** `cos pr conflicts --branch agents/a/s1` runs, **Then** it reports agents/b/s2 overlapping on foo.py and exits 0 (advisory, never blocks).
**Given** two agent branches that changed disjoint files, **When** conflicts runs, **Then** it reports no overlap.
**Given** the target branch has uncommitted changes to bar.py in its worktree and a peer branch committed bar.py, **When** conflicts runs, **Then** the uncommitted overlap is detected too (touched-files = merge-base diff ∪ worktree porcelain).

## Work Log
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: commit 3564a23b0c — feat(pr-mode): cos pr conflicts — early-warning file overlap across agent branches
- 2026-06-24 [claude]: Deliberation (Tool 6 risk + Tool 8 simplify): made conflicts ADVISORY-only (exit 0, never block) because two agents…
