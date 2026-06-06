---
id: TASK-213
title: "ROOT-5 multi-adapter session-marker drift \u2014 align adapter.yaml\u2194cos-env probe, guard with test, fix codex panel upgrade + doc"
swimlane: core
kind: bug
epic: agent-hub
labels: [multi-adapter, drift, hooks, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260605-233300-41f3
depends_on: []
blocked_by: []
references: []
---
# TASK-213: ROOT-5 multi-adapter session-marker drift — align adapter.yaml↔cos-env probe, guard with test, fix codex panel upgrade + doc

**Outcome (one sentence):** Close three multi-adapter session-marker drifts so the "data-driven / one central system, multi-adapter" contract is honest: (1) remove `ANTHROPIC_SESSION_ID` from claude adapter.yaml (declared but never probed by cos-env.sh::_cos_resolve_panel_id — TASK-112 dropped it from the probe); (2) add a regression test asserting every adapter.yaml runtime_session_marker.env_vars entry ∈ the cos-env.sh probe; (3) make codex-pretool-dispatch.sh call cos_panel_upgrade_from_payload so its Bash safety delegates run under the real panel id; (4) correct state-files.md's false probe-order ("GEMINI_SESSION_ID · ANTHROPIC_SESSION_ID") + "zero code change" claim.

## Read First
- src/core/hooks/cos-env.sh (_cos_resolve_panel_id probe loop ~150-151)
- src/adapters/claude/adapter.yaml (runtime_session_marker.env_vars ~69-71)
- src/adapters/codex/hooks/codex-pretool-dispatch.sh (INPUT=$(cat), no panel upgrade)
- docs/engineering/state-files.md (panel-id resolution §, line ~100)

## Repro Steps
1. Grep cos-env.sh: the probe loop lists only CLAUDE_CODE_SESSION_ID / CLAUDE_SESSION_ID / CURSOR_SESSION_ID / CURSOR_TRACE_ID / CODEX_SESSION_ID — NOT ANTHROPIC_SESSION_ID nor GEMINI_SESSION_ID.
2. Grep claude adapter.yaml: it declares ANTHROPIC_SESSION_ID as a runtime_session_marker env var → a marker the code never reads (silently dead); no test catches the mismatch.
3. Read codex-pretool-dispatch.sh: it reads INPUT=$(cat) but never calls cos_panel_upgrade_from_payload, so branch-guard/enforce-commit-message delegates resolve the panel via the ppid fallback instead of the stdin session_id.
4. Read state-files.md line ~100: it advertises a probe order including GEMINI_SESSION_ID + ANTHROPIC_SESSION_ID and claims "zero code change anywhere in src/core" to add an agent — both false.
Expected: adapter.yaml markers ⊆ cos-env probe; codex delegates run under the real panel; docs match code.
Actual: ANTHROPIC declared-not-probed; codex on ppid fallback; doc overstates.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the adapter registry and the cos-env.sh panel-id probe
- **When** the new parity test runs and a codex Bash PreToolUse fires
- **Then** every adapter.yaml runtime_session_marker.env_vars entry is present in the cos-env.sh probe (test green; claude no longer declares the unprobed ANTHROPIC_SESSION_ID), codex-pretool-dispatch.sh upgrades the panel from stdin before delegating, state-files.md states the true probe order + the honest "add the env var to the probe + adapter dir" contract, and `make verify-hooks` + the new test are green.

## Work Log
- 2026-06-06 [claude]: Fixed ROOT-5 drift: removed dead ANTHROPIC_SESSION_ID from claude adapter.yaml; added tests/test_adapter_session_marker_
- 2026-06-06 [claude]: committed 008b240e: docs/engineering/state-files.md, src/adapters/claude/adapter.yaml, src/adapters/codex/hooks/codex-pr
