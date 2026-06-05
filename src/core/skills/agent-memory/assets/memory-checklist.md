<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# Agent-Memory Checklist

Use when writing to or reading from agent memory.

## Before writing an observation
- [ ] It's a breakthrough / failure mode / non-obvious decision / cross-session fact — not a recap.
- [ ] NOT already in code (`cos_graph_*`/Read), docs (`cos_doc_search`), or git history.
- [ ] `type` is one of pattern/workflow/error/decision/discovery.
- [ ] confidence sensible (0.5 default; 0.8+ only after a 2nd confirmation).
- [ ] No PII, no secrets — `python3 scripts/check_observation.py --file obs.json` → `ok`.
- [ ] Tagged with domain/swimlane when known.

## When reading (Orient phase)
- [ ] `cos_search(..., min_confidence=0.3, since_days=90)` for recent high-trust patterns.
- [ ] `cos_learn_suggest(task_id=...)` for task-relevant patterns.
- [ ] Zero hits → fall through to docs, then code.

## Hygiene
- [ ] Code beats memory on conflict — stale observation updated/deleted, not trusted.
- [ ] Confidence not inflated (pollutes ranking).
- [ ] Audit-log events (`cos_audit_log_record`) kept separate from operational memory.
