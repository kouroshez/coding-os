---
status: in_progress
slug: cognition-loops
created: 2026-05-29
owner: claude
epic: cognitive-telemetry
---

# Audit — Cognition / Learning Loops Are Plumbed But Starved

**Verdict:** Every storage table, the nightly launchd job, all MCP tools and
hooks exist and run. Nothing is broken-wiring. The failure is *upstream of
storage*: auto-writers hardcode constants or omit high-value columns;
signal-rich writers are agent-invoke-only and never auto-triggered; the
observation faucet is reaped before commit; the pattern-miner mines only
failure signal the system never produces.

Diagnosis verified by: code read + DB inspection + live in-vivo probe
(scratch Write → `capture-observation [fire]` → observations stayed 2, no
error log) + a 4-agent adversarial verification workflow (`wlavrbo9e`) + a
graph-vs-direct cross-check.

## Scope rule (Rule 22)

User directive: implement **everything that is NOT overengineering**. Items
classified `IMPLEMENT` are real bugs with surgical, current-value fixes.
Items classified `DORMANT` would add speculative surface (new auto-trigger
mechanisms / enforcement gates with no current caller) — documented here,
**not built**.

## Category table

| # | Group | Finding | Sev | Root cause (file:line) | Class |
|---|---|---|---|---|---|
| 1 | G1 capture | observations never persist (bg reaped) | CRIT | `capture-observation.sh:47-49` detach + `capture.py:343` swallows stderr | IMPLEMENT |
| 2 | G2 outcome | outcome hardcoded `success`, skills/model/duration omitted | HIGH | `board_commands.py:447`, `record_outcome.py:119` | IMPLEMENT |
| 3 | G2 outcome | MCP `cos_task_move(complete)` records no outcome | MED | `board_os/mcp_tools.py:617` | IMPLEMENT |
| 4 | G3 miner | `learn_extract` failure-only, no success mining | HIGH | `learning.py:156-289` | IMPLEMENT |
| 5 | G4 metrics | `agent_metrics` 389× hardcoded constants | HIGH | `session_enrich.py:137` | IMPLEMENT |
| 6 | G4 summary | `session_summaries` husks (semantic writer 0 callers) | HIGH | `session-end.sh` ↮ `record_review.py` | IMPLEMENT |
| 7 | G5 routing | `routing_weights` empty (needs model col) | HIGH | unblocked by #2 | IMPLEMENT (verify) |
| 8 | G6 roles | `cos_compose_chain` never writes `.roles`/`.role` (dead fast-path) | MED | `cognition.py:877` | IMPLEMENT |
| 9 | G6 roles | `/chain` blind to real `cos_supervise` activity; hard empty state | MED | `web/routes/roles.py`, `RolesPage.tsx` | IMPLEMENT |
| 10 | G7 doctor | `health_check.mcp_server_configured` false-negative (`thinking_os` vs `coding-os`) | LOW | `health_check.py:369` | IMPLEMENT |
| 11 | G7 doctor | admin doctor view shows counts only, not self-diagnosis/degeneracy | MED | web doctor route | IMPLEMENT |
| 12 | G8 hooks | `auto-reindex-docs [skip] no_core_dir` | LOW | hook env resolution | IMPLEMENT (investigate) |
| 13 | G8 hooks | `auto-prune-deleted-files [skip] script_missing` | LOW | missing script ref | IMPLEMENT (investigate) |
| 14 | G9 graph | `learn_extract` refs 34 vs 36 (MCP→impl edge missed); `server_stale=true` | HIGH | stale MCP server / resolver | IMPLEMENT (reindex+reverify; code-fix only if persists) |
| D1 | dormant | experiment_log / doc_audit_trail / ambiguity_violations auto-triggers | LOW | manual-only writers | DORMANT |
| D2 | dormant | backtrack auto-capture from tool-failure hook | LOW | new capture surface | DORMANT |
| D3 | dormant | `cos_retrieval_cite` auto-detection of "doc was used" | LOW | undetectable cheaply | DORMANT |
| D4 | dormant | Rule-15 compose_chain enforcement nudge/gate | LOW | speculative | DORMANT |
| D5 | dormant | full CI data-quality harness | LOW | over-surface | DORMANT (minimal flag in #11 instead) |
| — | n/a | RTK lossy Bash-output compression | n/a | external `~/.claude` tooling | NOT-OURS |

## Grouped implementation checklist

### G1 — Capture pipeline [CRIT]
- [ ] `capture.py`: emit stderr + non-zero on real failure (un-swallow `main()` bare except) so `.capture-errors.log` net works.
- [ ] `capture.py`: gate the embedding step behind `COS_CAPTURE_SKIP_EMBED` (FTS5 trigger already indexes on INSERT) so the hot path can't block on model load.
- [ ] `capture-observation.sh`: run the insert **synchronously** (commit can't be reaped) with embed-skip; keep it <~30ms.
- [ ] VERIFY: scratch Write → observations count increments + row visible (live re-probe).

### G2 — Outcome capture quality [HIGH]
- [ ] `record_outcome`: accept + persist `skills_used` (from `.active-skill`), `model`, `duration_min`; honor real `outcome` arg.
- [ ] `board_commands.py:_record_brain_outcome_safe`: pass real skills/model/duration; stop unconditional `success`.
- [ ] `cos_task_move(to=complete)`: invoke `_record_brain_outcome_safe` so MCP completions feed the loop.
- [ ] VERIFY: a task-done writes a row with non-null skills/model.

### G3 — Learn from success [HIGH]
- [ ] `learn_extract`: add minimal positive-signal mining (success-rate baseline by domain/complexity + `outcome_history.is_breakthrough`). Extend, don't fork (Rule 22).
- [ ] VERIFY: with ≥3 success outcomes, `extracted` is non-empty; nightly produces ≥1 pattern.

### G4 — De-degenerate writers [HIGH]
- [ ] `session_enrich.py`: derive `agent_type/outcome/complexity/model` from real session state, not literals.
- [ ] session-end: populate `session_summaries` semantic fields from the work-log (no LLM); stop writing husks.
- [ ] VERIFY: new agent_metrics row not `session/opus/success`; new session_summary has non-blank fields.

### G5 — Routing weights [HIGH]
- [ ] Confirm `routing_weights` forms once `task_outcomes.model` is populated (G2). No code unless still empty.

### G6 — Roles / cognition [MED]
- [ ] `cos_compose_chain`: write `.roles` (chain json) + `.role` (lead) via `write-state.sh` → `$COS_PANEL_DIR`.
- [ ] `web/routes/roles.py /chain`: also derive activity from `role_dispatch`/`role_output_recorded` trace events.
- [ ] `RolesPage.tsx`: reframe empty state to show the 11 role defs + recent outputs.
- [ ] VERIFY: `/api/roles/chain` reflects a real supervised session.

### G7 — Doctor / health surfacing [LOW/MED]
- [ ] `health_check.py`: fix MCP key check (`coding-os`).
- [ ] admin doctor view: surface `health_check` issues + flag any wired table with 1 distinct value across >N rows (minimal degeneracy guard).

### G8 — Hook fixes [LOW]
- [ ] `auto-reindex-docs`: fix `no_core_dir` skip.
- [ ] `auto-prune-deleted-files`: restore/repoint missing script.

### G9 — Graph hardening [HIGH]
- [ ] `cos graph-reindex` + restart MCP; re-query `learn_extract` references.
- [ ] If `server.py:783` + `bootstrap_outcomes.py:160` edges still missing → resolver fix + regression test. Else: staleness only, surface `server_stale` warning.

## Resume marker
Not started — checklist authored. Next: G1 (capture, CRIT).
