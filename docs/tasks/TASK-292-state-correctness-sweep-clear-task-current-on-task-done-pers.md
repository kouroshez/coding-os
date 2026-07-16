---
id: TASK-292
title: "State-correctness sweep: clear .task-current on task-done, persist board view across refresh, codex Stop-hook parity, commit-link perf"
swimlane: core
kind: bug
epic: panel-state-isolation
labels: [state-isolation, board, hooks, perf, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-292: State-correctness sweep: clear .task-current on task-done, persist board view across refresh, codex Stop-hook parity, commit-link perf

**Outcome (one sentence):** Task-current is auto-cleared when a task leaves active work (no fossils, correct commit attribution); the board swimlane/flat toggle survives refresh; drain-embedding-outbox runs for Codex; the commit-link hook fast-paths out on non-commit Bash.

## Read First
- src/core/hooks/sync-task-current.sh
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/hooks/link-commit-to-task.sh
- src/adapters/codex/adapter.yaml

## Repro Steps
1. Run `cos task-done TASK-X`; observe `.task-current` still points at TASK-X (sync-task-current only sets on in_progress, never clears) → fossils + wrong commit attribution.
2. In the Hub board, toggle swimlane→flat, refresh the page; the view resets to swimlanes (tweaks.showSwimlanes is not persisted, unlike cos-zoom/cos-collapsed-lanes).
3. `uv run pytest tests/test_adapter_parity.py` is red on drain-embedding-outbox (Stop/*) not wired for Codex.
Expected: marker clears on done; board view persists; parity green.
Actual: stale marker; view resets; parity red.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an active `.task-current=TASK-X`, **When** the panel runs `cos task-done TASK-X` / moves it to complete/done/archived/blocked, **Then** sync-task-current clears the marker (only when it points at TASK-X).
- **Given** the board set to flat, **When** the page is refreshed, **Then** the flat/swimlane choice persists (localStorage, like zoom/collapsed-lanes).
- **Given** Codex Stop, **When** a turn ends, **Then** drain-embedding-outbox runs (wired into the codex stop dispatcher) and test_adapter_parity is green.
- **Given** any non-commit Bash command, **When** link-commit-to-task fires, **Then** it exits before spawning python (raw-payload fast-path).

## Work Log
- 2026-06-09 [claude]: Fixed: (B) sync-task-current.sh now clears .task-current on task-done/move-to-complete|done|archived|blocked (rm the per
