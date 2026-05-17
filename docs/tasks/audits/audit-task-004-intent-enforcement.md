---
audit_id: task-004-intent-enforcement
task_id: TASK-004
intent_detected_at: 2026-05-17T02:00:00Z
matched_exhaustive: ["", "", ""]
matched_scope: ["fix", "audit", "verify"]
predicates: ["coverage_100", "iterate_until_zero_residual", "strict_zero_residual", "all_categories_evidence"]
status: in_progress
created: 2026-05-16
completed: null
---

# Audit: TASK-004 Intent Enforcement Layer — 15-Group Implementation

## Source Intent

**User prompt (quoted):**

> "
> ...
> -"

**Matched exhaustive vocabulary:** , ,
**Matched scope verbs:** fix, audit, verify (implied: , )
**Predicates to satisfy:** coverage_100 (all 15 groups), iterate_until_zero_residual (loop on test failure), strict_zero_residual (no group left incomplete), all_categories_evidence (per-group commit + work-log entry)

## Categories — Mandatory Coverage Table

Each group = one category. `Hits before` = group not yet implemented (=1). `Hits after` = remaining incomplete (=0 when committed). `Verified` = commit landed + tests/manual green.

| # | Category | Pattern (deliverable) | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|
| 1 | G10 vocab doc | docs/engineering/intent-vocabulary.md | 1 | 1 | yes | 0 | yes | 059f113 |
| 2 | G0 SessionStart primer | src/core/hooks/intent-primer.sh | 2 | 1 | yes | 0 | yes | c2a3e7f |
| 3 | G1 per-prompt detector | detect-exhaustive-intent.sh + extract_intent.py + test_intent_classifier.py | 3 | 1 | yes | 0 | yes | 170efe0 |
| 4 | G12 audit artifact + enforcement | template + enforce-audit-artifact.sh + inject-resume-prompt.sh | 3 | 1 | yes | 0 | yes | 26432e9 |
| 5 | G3 EvidenceBundle schema | ExhaustiveEvidence + validate_exhaustive_evidence + cos_supervise_record_output extension | 4 | 1 | yes | 0 | yes | (this commit) |
| 6 | G4 completion_guardian | completion_guardian.py + verify-completion-claim.sh + test_completion_guardian.py | 3 | 1 | yes | 0 | yes | (this commit) |
| 7 | G5 anti-completion-bias | prevent-premature-done.sh (per-session debounced nudge — defer expected_tool_counts.py per Rule 22 until proven needed) | 1 | 1 | yes | 0 | yes | (this commit) |
| 8 | G6 auto-reviewer | reviewer spawn on cos_task_move --to done | 0 | 1 | no | 1 | no | (pending) |
| 9 | G7 count-grounding | enforce-count-grounding.sh | 0 | 1 | no | 1 | no | (pending) |
| 10 | G2 audit_exhaustive formula | roles/presets/registry.yaml chain | 0 | 1 | no | 1 | no | (pending) |
| 11 | G8 subagent delegation | enforce-subagent-delegation.sh | 0 | 1 | no | 1 | no | (pending) |
| 12 | G9 task-class verification matrix | rules/test-discipline.md extension + hook | 0 | 1 | no | 1 | no | (pending) |
| 13 | G11 learning loop | observation_record + metric + auto-tune | 0 | 1 | no | 1 | no | (pending) |
| 14 | G13 Hub UI audits tab | FastAPI route + React component | 0 | 1 | no | 1 | no | (pending) |
| 15 | G14 CI trace-replay assertion | cognition trace-replay extension + workflow | 0 | 1 | no | 1 | no | (pending) |
| 16 | G15 auto-mode-vs-exhaustive | rule doc + enforcement hook | 0 | 1 | no | 1 | no | (pending) |

## Resume Marker

<!-- last_updated_row: 7 -->
<!-- next_unchecked_row: 8 -->
<!-- last_updated_at: 2026-05-17T04:30:00Z -->

## Notes

- 3-layer intent architecture from G0/G1/G12 is live in .claude/ via
  install.sh after each Wave commit.  System now eats its own dogfood:
  the very next exhaustive prompt fires the new detector + writes
  intent.json, and any subsequent code edit without an audit artifact
  (i.e. this file's absence) would be blocked by G12.
- Wave 1 found two stale src-layout migration bugs out of scope for this
  task: Makefile `docs-lint` target gone; src/scripts/regen_doc_index.py
  has `from tools.docs` import error.  Logged in work log; defer to a
  separate task.
- Wave 1 also patched src/core/hooks/enforce-wip-limit.sh to exclude
  docs/tasks/audits/* (false positive — audit files are not task cards).
- Wave 2 (G3-G7) starts next — schema migration first, then guardian,
  then nudge, then reviewer, then count-grounding.
- Wave 3 (G2,G8,G9,G11,G13-G15) follows once Wave 2 evidence pipeline
  is proven.

## Closing Checklist (the guardian asserts these)

- [ ] Every category row has non-empty `Files scanned`
- [ ] Every category row has `Hits after = 0`
- [ ] Every category row has `Verified = yes`
- [ ] Every category row has a non-empty `Evidence` cell
- [ ] EvidenceBundle submitted via `cos_supervise_record_output` (Wave 2)
- [ ] Reviewer subagent re-grep produced zero hits (Wave 2)
- [ ] Frontmatter `status` updated to `completed` and `completed` date filled
