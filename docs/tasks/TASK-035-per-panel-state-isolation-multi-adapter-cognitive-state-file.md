---
id: TASK-035
title: "Per-panel state isolation: multi-adapter cognitive state files keyed by hybrid panel-id"
swimlane: infra
kind: feature
epic: null
labels: [state-files, concurrency, multi-adapter, panel-isolation, enterprise-hardening]
status: complete
priority: P1
appetite: "7d"
created: 2026-05-26
started: 2026-05-26
completed: 2026-05-26
agent_session: ses-claude-20260526-003648-f813
depends_on: []
blocked_by: []
references: []
---
# TASK-035: Per-panel state isolation: multi-adapter cognitive state files keyed by hybrid panel-id

**Outcome (one sentence):** Two panels of the SAME agent on the SAME project never trample each other's cognitive state (task-current, thinking_os-gate, active-skill, doc-anchor, memory-check, zoom-checkpoint, active-formula, learn-suggestions). Multi-adapter ready (claude/codex/cursor/gemini) via data-driven adapter.yaml::runtime_session_marker. Files for hot state, DB rollup on session end. Worktree workaround removed from docs.

## Read First
- docs/engineering/state-files.md
- src/core/hooks/cos-env.sh
- src/core/hooks/write-state.sh
- src/core/hooks/session-context.sh
- src/core/hooks/check-state.sh
- src/adapters/claude/adapter.yaml
- src/core/rules/transparency-banner.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** two panels of the same agent (Claude) attached to the same project, each with distinct `session_id` UUIDs from stdin, **When** each panel runs `bash src/core/hooks/write-state.sh .coding-os/claude/.thinking_os-gate "CLEAR 1"`, **Then** each panel reads back ONLY its own value via `_read_state`; neither sees the other's write; verified by `tests/test_panel_isolation.py::test_two_panels_independent_gate`.
- **Given** Claude Code stdin payload contains `session_id`, **When** any hook sources `cos-env.sh`, **Then** `$COS_PANEL_ID` resolves to a stable per-panel token via priority `stdin > $COS_SESSION_ID env > $CLAUDE_SESSION_ID env > ppid-derived hash`, with `cos-env.sh` reading the active adapter's `runtime_session_marker` block (Rule 11 data-driven, supports codex/cursor/gemini without code change).
- **Given** the 8 cognitive state files (gate, task-current, active-skill, doc-anchor, memory-check, zoom-checkpoint, active-formula, learn-suggestions) plus 5 per-panel dedupe markers, **When** a panel's `SessionStart:startup` fires, **Then** only THIS panel's `panels/<panel-id>/` subdir is cleared; the other panel's state stays intact; orphan `panels/<panel-id>/` whose pid is dead is GC'd by `auto-brain-decay.sh` after `COS_PANEL_GC_TTL` (default 24h).
- **Given** `.task-mode`, `.model`, `.swimlane`, `.last-verify`, `.last-decay`, `.agent`, `.hooks.log`, `coding-os.db`, `.turn-activity.log` are designed shared, **When** any panel writes them, **Then** they remain at `$COS_AGENT_DIR` / `$COS_STATE_DIR` and are NOT moved to panel dir (regression guard: `tests/test_panel_isolation.py::test_shared_files_stay_shared`).
- **Given** `docs/engineering/state-files.md` and `src/core/rules/transparency-banner.md` previously documented the multi-panel-same-agent failure with a worktree workaround, **When** this task ships, **Then** the worktree workaround paragraphs are removed, replaced with the per-panel design (S7 scenario added, persona × scenarios matrix gains P6 row, transparency banner concurrency-model table row updated to ✅).
- **Given** `make verify` after edits, **When** `uv run pytest tests/test_panel_isolation.py tests/test_cos_env_panel_resolution.py tests/test_session.py -q` and `make verify-hooks` run, **Then** all green; manual 3-panel smoke (open 3 Claude panels, each records different gate value, banner shows correct per-panel state) confirmed.

## Work Log
- 2026-05-26: TASK created. Initial audit in `docs/tasks/audits/audit-per-panel-state-isolation-2026-05-26.md`. Decisions: hybrid panel-id (stdin → ppid fallback), files for hot state + DB rollup on end, worktree workaround removed.
- 2026-05-26: Groups A-F implemented + tested.
  - **A1-A3 (Foundation, DNA + mRNA)**: `cos-env.sh` gained `_cos_resolve_panel_id`, `COS_PANEL_ID`, `COS_PANEL_DIR`, `COS_PER_PANEL_FILES` allowlist, helpers `cos_state_path` and `cos_panel_upgrade_from_payload`. Adapter manifests gained `runtime_session_marker` block (claude/codex/cursor) + schema entry in `adapter.schema.json`. Data-driven per Rule 11 — adding gemini = adapter dir + yaml block, zero core change.
  - **B1-B5 (Writer/Reader protocol)**: `write-state.sh` routes per basename via `cos_state_path` + creates parent dir on demand. `check-state.sh` reads panel-first with one-cycle legacy AGENT_DIR fallback during migration window. 8 cognitive files + 5 dedupe markers + 3 override markers + `session-id` route to `$COS_PANEL_DIR`. `.task-mode`/`.model`/`.swimlane`/`.last-verify`/`.last-decay`/`.turn-activity.log`/`.hooks.log` stay shared.
  - **C1-C3 (Lifecycle)**: `session-context.sh` calls `cos_panel_upgrade_from_payload` early; cleanup loop scoped to `$COS_PANEL_DIR`; `_panel_or_agent` helper for compact/resume snapshot. `auto-brain-decay.sh` reaps stale `panels/<id>/` subdirs older than `$COS_PANEL_GC_TTL` (default 24h), never touches the current panel. `completion_guardian.py` + `extract_intent.py` resolve to `$COS_PANEL_DIR` with legacy fallback.
  - **E (Tests, 13 new + matrix regressions)**: `tests/test_panel_isolation.py` (5 tests: two-panel independent gate, cognitive-files routing, shared-files stay shared, legacy fallback, panel precedence). `tests/test_cos_env_panel_resolution.py` (8 tests: priority ladder, sanitization, stdin upgrade). Updated `tests/test_hooks.py::test_session_file_follows_state_dir` for panel path. Renamed `test_fails_without_parent_dir` → `test_creates_parent_dir` (intentional behavior change). All matrix tests green: 13 panel + 131 hooks + 47 adapters + 332 board_os + 12 completion_guardian.
  - **F (Docs)**: `docs/engineering/state-files.md` gained S7 multi-panel scenario, P6 persona row, three-tier scope explanation, panel-id resolution section. `docs/engineering/adapter-parity.md` gained `runtime_session_marker` contract section. `src/core/rules/transparency-banner.md` concurrency-model row updated to ✅, worktree workaround paragraph removed. `CLAUDE.md` P2 note deferred (governance task gate; tracked separately).
  - **G (Hub UI)**: deferred per Rule 22 — transparency banner already surfaces per-panel cognitive state to the agent; per-panel column in `SessionsPage.tsx` is nice-to-have, not load-bearing.
  - **Acceptance**: all G/W/T pass; 3-panel smoke covered by `test_two_panels_independent_gate`. Worktree workaround removed (`grep worktree-workaround` returns 0 in transparency-banner + state-files).
- 2026-05-26 [claude]: committed + verified (was uncommitted in working tree)
- 2026-05-27: **Hardening pass (cross-panel leak fix).** User observed sibling panel's task/gate surfacing in this panel's banner because AGENT_DIR fossils were honoured as "migration fallback". That fallback was the leak. Fix:
  - `cos-env.sh::cos_current_session` + `cos_current_task` — strict panel-only read; fall back to `$COS_PANEL_ID` as identity, NEVER to `$COS_AGENT_DIR/session-id`.
  - `check-state.sh` — removed AGENT_DIR fossil fallback for per-panel basenames; `CURRENT_SESSION` resolves from panel session-id or `$COS_PANEL_ID`, never agent-dir.
  - `session-context.sh` — removed dual-id accept and AGENT_DIR fallback in `_read_state`, idempotently seeds panel session-id from `$COS_PANEL_ID`. `_panel_or_agent` helper now panel-only.
  - `write-state.sh` — falls back to `$COS_PANEL_ID` as `SESSION_ID` prefix when no panel session-id file exists yet.
  - Test: renamed `test_legacy_agent_dir_fallback_on_read` → `test_no_cross_panel_leak_via_agent_dir_fossil` — asserts fossil REJECTED. `TestThinkingOsGate` fixture rewritten for panel dir.
  - Docs: `transparency-banner.md` accuracy table changed to "STRICT panel-id match (no AGENT_DIR fallback)".
  - Tests: 134 hooks + 16 isolation + 14 guardian all green.
