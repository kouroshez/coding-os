---
id: TASK-675
title: "Merge the UserPromptSubmit nudge hooks into one read-stdin-once dispatcher (revive archived TASK-082, de-risked by F1)"
swimlane: core
kind: refactor
epic: hook-consolidation
labels: [hooks, nudge, dispatcher, ready]
status: archive
priority: P2
appetite: 2d
created: 2026-06-30
started: null
completed: null
agent_session: ses-claude-20260630-011740-9a32
depends_on: [TASK-672]
blocked_by: []
references: []
---
# TASK-675: Merge the UserPromptSubmit nudge hooks into one read-stdin-once dispatcher (revive archived TASK-082, de-risked by F1)

**Outcome (one sentence):** The UserPromptSubmit nudge hooks that each re-read prompt stdin separately (nudge-thinking-os, nudge-graph-os, nudge-docs-first, nudge-task-discovery, nudge-reuse-first, nudge-model-routing, nudge-git-mode) collapse into one read-stdin-once dispatcher, reviving the deliberately-archived TASK-082 now that the F1 (TASK-672) behavior-parity harness can prove the merge preserves each nudge's output.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/nudge-thinking-os.sh
- src/core/hooks/nudge-docs-first.sh
- src/adapters/codex/adapter.yaml
- docs/playbooks/hook-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the F1 parity harness baseline, **When** the nudge hooks merge into one dispatcher, **Then** each former nudge's (input)→(additionalContext) output matches its baseline.
- **Given** the merged dispatcher, **When** a UserPromptSubmit fires, **Then** prompt stdin is read once rather than once per nudge, and per-nudge debounce markers still work.
- **Given** the Codex Bash-only dispatcher, **When** the merge lands, **Then** registry, adapter templates, and goldens regenerate green and parity is preserved.

## Work Log
