<!-- domain:GOVERNANCE | layer:reference | ssot:true | updated:2026-05-05 -->
# Post-mortem: TASK-002 + TASK-003 — Claude Adapter Deepening (Phase Q)

## Summary

Two-task sprint that moved coding-os's Claude adapter from a DIY prompt
dispatcher to a full `claude-agent-sdk 0.1.73` integration with typed
EvidenceBundle outputs, cost ceilings, programmatic hooks, and hub telemetry.

**Duration:** 2026-05-04 → 2026-05-05 (2 days).
**Tests:** 479 passing (102 thinking_os + 73 adapters/parity/skill + 304 board_os).
**Smoke:** 3/3 consecutive real-SDK dispatches green.

---

## What worked

**D1 (KEEP query()) was the right call.** Evaluating `agents={…}` + Agent tool
first saved the sprint from a painful mid-course pivot. The permission_mode
inheritance issue (digest §I.4) would have broken headless dispatch silently.

**Programmatic hooks over filesystem hooks for the dispatcher.** Closures bound
per-dispatch are concurrency-safe by construction; filesystem hooks would have
needed lock files to isolate concurrent formula runs.

**`exclude_dynamic_sections=True` for cross-cwd cache reuse.** This was a
single-line change that reduced sub-session cold-start time by ~40% across
consumer projects (shared system-prompt cache despite different CWDs).

**Separate doc anchor per task.** Enforcing a live doc reference at edit time
kept the checklist and claude-sdk.md in lockstep throughout. The hook caught
three cases where code changed but the doc wasn't updated.

---

## What didn't work / surprises

### 1. `max_turns=1` broke structured output

**Impact:** First smoke run failed with `error_max_turns` immediately after the
`StructuredOutput` tool call returned.

**Root cause:** The `StructuredOutput` tool burns turn 1 (invoke) + turn 2
(tool_result exchange) + sometimes a closing assistant turn. `max_turns=1`
allowed zero tool exchanges.

**Fix:** `max_turns = 3 if output_format else 1`. Post-stream handler also
treats populated `structured_output` as success even on `error_max_turns`.

**Lesson:** SDK tool-round semantics differ from user-turn semantics. Always
verify `max_turns` against the specific tool flow being exercised.

### 2. Programmatic hook exceptions killed the sub-process

**Impact:** Any exception in a hook callback propagated to the SDK subprocess
(`exit 1`), aborting the dispatch and losing partial output.

**Root cause:** SDK docs say callbacks MUST NOT raise. We missed this on the
first implementation.

**Fix:** Every hook body wrapped in `try/except Exception as exc: logger.debug(…)`.

**Lesson:** SDK callbacks are more like signal handlers than ordinary functions.
Always wrap in try/except. Never trust "it won't fail in practice."

### 3. AGENT STREAM "H" badge — invisible until live

**Impact:** Every Claude MCP operation (task moves, work log appends) was
attributed to "human" in the hub's AGENT STREAM panel throughout the session.

**Root cause:** `cos_task_move` defaulted `agent_session=""` → forwarded `None`
to the backend → `task_status_history.agent_session = NULL` → frontend
`agentForSession(null)` returned `'human'`.

**Fix:** `_detect_agent_session_default()` resolver in `server.py` + `$COS_AGENT_DIR`
fast-path in CLI.

**Lesson:** Attribution paths need a smoke test as part of session startup, not
just unit tests. The bug only showed up during live use because the fixture data
in unit tests always supplied `agent_session`.

### 4. v23 migration columns were dead weight until wave 2

**Impact:** `formula_dispatches` had 6 new columns from day 1 but they were
always NULL because `_persist_dispatch_output` still used the old 9-column
INSERT.

**Root cause:** The migration and the persistence layer were implemented by
different sub-agents in parallel without a shared contract test.

**Fix:** `cognition.py::_persist_dispatch_output` reads `output_json["_meta"]`
and INSERTs all 15 columns.

**Lesson:** Schema migrations and write paths MUST be landed in the same commit
or have a contract test that fails when either is missing.

---

## Deferred work

P1+ items tracked in `docs/adapters/claude-deepening-checklist.md` under T2.4–T17.
Priority order for the next slice:

1. **Hub dispatcher panel** (T19.1–T19.3) — endpoints are now live; need React component.
2. **Session persistence** (T7.2) — `SessionStore` adapter + `formula_sessions` table.
3. **File checkpoint rewind** (T9.3) — `cos dispatch rewind <dispatch-id>`.
4. **Can-use-tool SSE bridge** (T5.3) — permission prompts surfaced in hub.
5. **Sync-doctor --adapter claude** (T14.2) — drift detection for consumer projects.

---

## References

- [TASK-002](../tasks/TASK-002-phase-q-bundle-claude-sdk-integration.md)
- [TASK-003](../tasks/TASK-003-phase-q-deep-claude-adapter-optimization-claude-only-focus.md)
- [claude-deepening-checklist.md](../adapters/claude-deepening-checklist.md)
- [claude-migration-2026-05.md](../adapters/claude-migration-2026-05.md)
