---
audit_id: workflow-integrity-gaps
task_id: TASK-080
intent_detected_at: 2026-06-04T00:00:00Z
matched_exhaustive: ["", "", "", "", ""]
matched_scope: ["fix", "verify"]
predicates: ["all_gaps_fixed", "each_tested", "reviewed", "committed_clean"]
status: in_progress
created: 2026-06-04
completed: null
---

# Audit: Workflow-Integrity Gap Fixes (hooks · compaction · codex · memory · cron · web)

## Source Intent

User asked (paraphrased, non-quoted): write a grouped checklist of all
identified workflow-integrity gaps, implement and completely fix every
one, test each individually, run /review, and commit everything clean.
Two scope decisions confirmed via AskUserQuestion: cron → responsive +
configurable from web panel; Codex server-side enforcement backstop →
deferred (Option A, matches CLAUDE.md).

**Matched exhaustive vocabulary:**  ·  ·  ·  ·
**Matched scope verbs:** fix · verify
**Predicates to satisfy:** every gap fixed · each group tested per matrix · reviewed · committed clean

## Categories — Mandatory Coverage Table

Implementation-task adaptation: "Hits before" = gap present (1).
"Hits after" = residual gap after fix+test (target 0). "Verified" =
matrix verification command green for that group.

| # | Category (gap group) | Pattern (fix + verification) | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|
| 1 | Hook ordering non-deterministic | renderer sorts per-(event,matcher) by category precedence, stable by declaration index; regen + golden | hook_renderer.py, registry.yaml, golden | 1 | yes | 0 | yes | 2014540 — test_golden_parity[claude] + test_hook_renderer green |
| 2 | session-skill-primer not re-fired on compaction | add `compact\|resume` event in registry; regen templates | registry.yaml, settings.template.json | 1 | yes | 0 | yes | b07a009 — claude SessionStart compact\|resume group has session-skill-primer; golden green |
| 3 | Codex dispatcher parity — Bash-runnable SessionStart/UPS hooks omitted | add intent-primer, rules-primer, session-skill-primer, inject-resume-prompt, warn-graph-empty, auto-brain-decay, check-mcp-extras, detect-exhaustive-intent to codex dispatchers | codex/adapter.yaml, codex-*-dispatch.sh, hooks.template.json | 1 | yes | 0 | yes | 28232ff — dispatcher smoke (valid JSON, no leak, priming present) + golden[codex] + registry-integration green |
| 4 | observations lack access-ranking symmetry | migration v30 add last_accessed_at + access_count; bump on retrieval; wire memory.py ranking | database.py, migrations, memory.py | 1 | yes | 0 | yes | cb51b4a — test_db (85) + memory ranking (174) + g4 smoke (access bump 0→1) + MCP self-test |
| 5 | learning/decay not responsive nor configurable | scheduled config.py (enabled/hour/thresholds, validated); session-end responsive_extract trigger; nightly reads config | scheduled/config.py, responsive_extract.py, nightly.py, session-end.sh | 1 | yes | 0 | yes | e8328a2 — test_scheduled_config (9) + test_nightly (26) + golden green |
| 6 | no web-panel editing of scheduled config | GET/PATCH /api/scheduled/config/{slug} + Settings ScheduledMaintenance panel | web/routes/scheduled.py, web/ui SettingsPage | 1 | yes | 0 | yes | 3c5b469 — route import OK (endpoints registered) + ui-build tsc clean + vitest 30/0 |
| 7 | unbounded learned_patterns growth (no consolidation) | run_decay merges exact dups + prunes dormant prior-archived patterns (config archive_prune_days) | thinking_os/decay.py, scheduled/config.py, nightly.py | 1 | yes | 0 | yes | d291bc8 — test_decay (27, +4 consolidation) + scheduled (35) + MCP self-test |

## Deferred (filed, NOT in this audit's scope — justified)

- **Codex server-side enforcement backstop** — large (~40 MCP tools), multi-day, risks breaking every adapter. User chose defer (Option A). → separate TASK.
- **Merge 4 UserPromptSubmit nudge hooks** — risky refactor, low ROI (hooks already per-session debounced). Anti-overengineering. → separate TASK.

## Resume Marker

<!-- last_updated_row: 7 -->
<!-- next_unchecked_row: none -->
<!-- last_updated_at: 2026-06-04T00:00:00Z -->
<!-- commits: G1=2014540 G2=b07a009 G3=28232ff G4=cb51b4a G5=e8328a2 G6=3c5b469 G7=d291bc8 -->
<!-- remaining: none — all 7 rows verified; deferred items filed below -->

## Notes

Each group = one trunk commit (explicit paths). Verify per matrix before
flipping Fixed→yes / Hits after→0 / Verified→yes. Order: G1, G2, G3
(adapter/template), G4 (migration), G5+G6 (cron+web), G7 (consolidation).

## Closing Checklist (the guardian asserts these)

- [ ] Every category row has non-empty `Files scanned`
- [ ] Every category row has `Hits after = 0` (or explicit `n/a` with justification in Notes)
- [ ] Every category row has `Verified = yes`
- [ ] Every category row has a non-empty `Evidence` cell
- [ ] EvidenceBundle submitted via `cos_supervise_record_output`
- [ ] Reviewer subagent re-grep produced zero hits
- [ ] Frontmatter `status` updated to `completed` and `completed` date filled
