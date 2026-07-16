---
id: TASK-812
title: "Add doctor rule_drift + doc_drift audit + Hub drift banner (F-D / rank 4)"
swimlane: core
kind: feature
epic: modularity-completion
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-07-16
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-812: Add doctor rule_drift + doc_drift audit + Hub drift banner (F-D / rank 4)

**Outcome (one sentence):** cos doctor + the Hub /api/settings/modules/drift endpoint surface a stranded module-tagged doc or module-owned rule left behind by an incomplete disable, so the enterprise/auditability persona can detect partial variability resolution instead of seeing a green doctor.

## Read First
- src/cli/doctor.py
- src/core/web/routes/settings.py
- src/cli/main.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a `| module:memory` doc still present while memory is disabled, **When** cos doctor runs, **Then** modules.doc_drift WARNs naming the file; same for a module-owned rule still linked (modules.rule_drift, after F-A ownership lands).

Checklist:
- [ ] _check_module_doc_drift in doctor.py: scan docs/ for a file-level `| module:<disabled>` header (reuse _DOC_MODULE_TAG_RE) or block-tagged content; WARN not FAIL.
- [ ] _check_module_rule_drift: a module-owned rule still symlinked while its module is disabled (depends on TASK-811 rules ownership).
- [ ] Wire both into doctor.py check registry AND settings.py drift endpoint (parity with skill_drift/command_drift) + Hub banner already renders drift rows.
- [ ] api-contract: drift row shape matches the existing DriftRow the UI consumes.
- [ ] Tests: doctor flags a planted stranded doc/rule; clean tree PASSes.
- [ ] Verify: uv run pytest tests/test_cli.py -q (doctor) + settings tests.

## Work Log
