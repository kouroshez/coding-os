<!-- domain:META | layer:asset | ssot:false | updated:2026-06-05 -->
# Agent-Memory Checklist

Use when reading from agent memory or running the learn loop. Writes are automatic
(edit-derived capture) — there is no freeform observation to hand-author.

## When reading (Orient phase)
- [ ] `cos_search(..., min_confidence=0.3, since_days=90)` for recent high-trust patterns.
- [ ] `cos_learn_suggest(domain=..., complexity=...)` for task-relevant patterns.
- [ ] `cos_details(pattern_id=..., source=...)` to drill into the top 1-2 (match `source` to the row's `source_table`).
- [ ] Zero hits → fall through to docs, then code.

## Learn loop
- [ ] `cos_learn_extract(min_occurrences=3)` to mint patterns from the task-outcome corpus.
- [ ] After using a suggested pattern, `cos_learn_validate(pattern_id, was_helpful)` so confidence tracks reality.
- [ ] Persistent rework on a domain+skill → `cos_learn_feedback(min_rework=3)` drafts guidance for human review.

## Hygiene
- [ ] Confidence is system-computed — never expect a write-time confidence knob.
- [ ] Code beats memory on conflict — a stale observation is re-verified against code, not trusted.
- [ ] No PII / no secrets in files whose edits get captured into a narrative.
- [ ] Audit-log events (`cos_audit_log_record`) kept separate from operational memory.
