# Audit — Memory Capture Pipeline Dead (2026-05-23)

Forensic root-cause for the `observations` table sitting at 2 stale rows from 2026-05-17 despite live session activity.

## Evidence (DB counts, 2026-05-23 05:46 UTC)

| Table | Rows | State |
|---|---|---|
| `observations` | 2 (both 2026-05-17, `tool_name='completion_guardian'`) | stale |
| `learned_patterns` | 0 | dead — nightly cron never ran |
| `doc_audit_trail` | 0 | dead — audit hook never fired |
| `session_summaries` | 52 (latest 2026-05-23 05:11) | live |
| `agent_metrics` | 263 (all `agent_type='session'`) | live |
| `task_outcomes` | 10 (latest 2026-05-23 02:15) | live |
| `formula_dispatches` | 2 (lifetime) | dead — see audit-roles-dead.md |
| `persona_selections` | 1 | dead |
| `file_index_state` | 2828 | live |

DB schema version 28. DB path `/Users/ciro/Files/Project/coding-os/.coding-os/coding-os.db` correct.

## Root Cause (confirmed)

`src/core/hooks/capture-observation.sh` line 28 (pre-fix) had a stale shell filter:

```bash
case "$TOOL_NAME" in
  Write|Edit) ;;
  *) exit 0 ;;
esac
```

The Python layer at [src/core/thinking_os/capture.py:31](../../../src/core/thinking_os/capture.py) declares `CAPTURE_TOOLS = {"Write", "Edit", "MultiEdit"}` with an explicit comment that excluding MultiEdit "meant most real agent edits produced zero observations." The shell filter was the stale layer — it dropped MultiEdit before `capture.py` could run.

Hook delivery itself was healthy: `[capture-observation] [fire] tool=Write` heartbeat was visible in `.coding-os/.hooks.log` (2026-05-23 05:49:44), proving the registry → adapter → settings.json render chain works. Failure was strictly inside the shell case-pattern.

## Secondary blockers (separate fixes)

| # | Issue | Fix in |
|---|---|---|
| 1 | ~~Nightly cron not installed~~ — CORRECTION (Phase-2 verify, 2026-05-23): `cos cron status` reports `installed: True`, `loaded: True`, last run 2026-05-22T07:00 with `learn_extract: ok`. Audit agent's "no launchd plist found" check looked at the wrong path. `learned_patterns=0` is the downstream symptom of having only 2 stale observations to extract from — once Phase 1 fix lands enough fresh observations, patterns will populate on next nightly. | n/a (already healthy) |
| 2 | `doc_audit_trail` empty — `cos_audit_log_record` invocation never triggered in any session. | follow-up task |
| 3 | Two existing observations from `tool_name='completion_guardian'` (not Write/Edit) — captured via direct MCP-tool call path, not the hook. Confirms capture.py write path works when reached. | n/a |

## Fix applied (TASK-016, commit 9dca67a)

Single-character change at `src/core/hooks/capture-observation.sh:28`:

```bash
case "$TOOL_NAME" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac
```

Smoke-tested via both paths (direct `python3 capture.py` + `bash capture-observation.sh`) — observation rows #3 and #4 written with `tool_name='MultiEdit'`. `make verify-hooks` clean.

## Open questions (for follow-up phases)

- **Why did the regression survive 6 days?** No regression test guards the shell-vs-python filter parity. Phase 2 should add `tests/test_capture_observation_hook.py` that pipes a MultiEdit payload into the hook and asserts a DB row.
- **`task_outcomes=10` but only 2 historical observations** — outcomes were captured via the work-log hook, not via observation_record. Distinct write paths; both should produce observations going forward.

## References

- [src/core/hooks/capture-observation.sh](../../../src/core/hooks/capture-observation.sh)
- [src/core/thinking_os/capture.py](../../../src/core/thinking_os/capture.py)
- [src/core/hooks/registry.yaml#L248](../../../src/core/hooks/registry.yaml) — capture-observation entry
- [docs/tasks/TASK-016-fix-capture-observation-multiedit-drop.md](../../tasks/TASK-016-fix-capture-observation-multiedit-drop.md)
