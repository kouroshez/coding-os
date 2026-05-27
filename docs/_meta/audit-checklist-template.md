<!-- domain:CORE | layer:template | ssot:true | updated:2026-05-16 -->
# Audit Checklist Template

> Template for compaction-resilient audit artifacts. Copy this file to
> `docs/tasks/audits/audit-<slug>.md` when the intent detector classifies
> the prompt as exhaustive (`.coding-os/<agent>/.intent.json::exhaustive=true`).
> The completion guardian, count-grounding hook, and auto-reviewer all read
> the copy as the canonical evidence record — chat output is volatile and
> evaporates after compaction.

When copying, replace the placeholder values (`<slug>`, `TASK-NNN`, ISO
timestamps, the prompt block) with real values from the active session.

> **Status form** — YAML frontmatter (`status: in_progress`) is
> canonical. The lifecycle consumers also accept legacy markdown bold
> (`**Status:** in_progress`) so historic audits keep working, but new
> audits MUST use the YAML form — it is the form `cos_supervise_record_output`
> + Hub UI + auto-reviewer all rely on.

---

```markdown
---
audit_id: <slug>
task_id: TASK-NNN
intent_detected_at: 2026-MM-DDTHH:MM:SSZ
matched_exhaustive: []
matched_scope: []
predicates: []
status: in_progress
created: 2026-MM-DD
completed: null
---

# Audit: <human-readable title>

## Source Intent

**User prompt (quoted):**

> (paste the exhaustive-intent prompt verbatim here so future you can
> re-derive scope without scrollback)

**Matched exhaustive vocabulary:** (from intent.json::matched_exhaustive)
**Matched scope verbs:** (from intent.json::matched_scope)
**Predicates to satisfy:** (from intent.json::predicates)

## Categories — Mandatory Coverage Table

Every category declared at start MUST end with `Verified=yes` and
`Hits after = 0` (or an explicit justified `n/a`). The completion
guardian rejects "done" if any row is incomplete.

| # | Category | Pattern (grep/AST/spec) | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|
| 1 | (fill) | (fill) | 0 | 0 | no | 0 | no | (fill) |

## Resume Marker

Resume-resilient pointer for cross-session continuation. Update on
every row change so a compacted session re-reads this file to know
where to continue.

<!-- last_updated_row: 0 -->
<!-- next_unchecked_row: 1 -->
<!-- last_updated_at: 2026-MM-DDTHH:MM:SSZ -->

## Notes

Free-form reasoning, blockers, decisions. Anything that influences
verification but does not fit the table columns.

## Closing Checklist (the guardian asserts these)

- [ ] Every category row has non-empty `Files scanned`
- [ ] Every category row has `Hits after = 0` (or explicit `n/a` with justification in Notes)
- [ ] Every category row has `Verified = yes`
- [ ] Every category row has a non-empty `Evidence` cell
- [ ] EvidenceBundle submitted via `cos_supervise_record_output`
- [ ] Reviewer subagent re-grep produced zero hits
- [ ] Frontmatter `status` updated to `completed` and `completed` date filled
```
