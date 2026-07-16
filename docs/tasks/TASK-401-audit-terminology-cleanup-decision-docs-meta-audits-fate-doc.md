---
id: TASK-401
title: "Audit terminology cleanup decision \u2014 docs/_meta/audits fate + doc_audit_trail naming"
swimlane: docs
kind: docs
epic: null
labels: [task-system-review, needs-user-decision, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-120804-a06f
depends_on: []
blocked_by: []
references: []
---
# TASK-401: Audit terminology cleanup decision — docs/_meta/audits fate + doc_audit_trail naming

**Outcome (one sentence):** User decides and we execute: (a) docs/_meta/audits/ forensic docs (referenced by ADR adr-role-dispatch-deferral + TASK-016/017/018/021/026) are either renamed to a non-audit term (e.g. _meta/forensics) with references updated, or deleted; (b) the doc_audit_trail table + capture-audit.sh + cos_audit_log_* tools (doc edit history — a DIFFERENT concept than the retired task-audit artifacts) either keep their name with the distinction documented, or are renamed to doc_history to end the terminology clash.

## Read First
- docs/_meta/audits/
- docs/governance/adr-role-dispatch-deferral.md
- src/core/hooks/capture-audit.sh
- src/core/thinking_os/tools/audit.py

## Work Log
- 2026-06-11 [claude]: Edit server.py
- 2026-06-11 [claude]: Edit server.py
- 2026-06-11 [claude]: Edit server.py
- 2026-06-11 [claude]: Edit prune_deleted_path.py
- 2026-06-11 [claude]: Edit sqlite_backend.py
- 2026-06-11 [claude]: Edit docs.py
- 2026-06-11 [claude]: Edit server.py
- 2026-06-11 [claude]: Edit registry.yaml
- 2026-06-11 [claude]: Edit _shared.py
- 2026-06-11 [claude]: Edit _shared.py
- 2026-06-11 [claude]: Edit database.py
- 2026-06-11 [claude]: Edit database.py
- 2026-06-11 [claude]: Edit health.py
- 2026-06-11 [claude]: Edit doctor-config.yaml
- 2026-06-11 [claude]: Edit test_hooks_workflow_integrity.py
- 2026-06-11 [claude]: Edit test_capture_and_prune_regressions.py
- 2026-06-11 [claude]: Edit test_doc_search_metadata_filters.py
- 2026-06-11 [claude]: Edit test_doc_search_metadata_filters.py
- 2026-06-11 [claude]: Edit test_db_integrity.py
- 2026-06-11 [claude]: Edit test_envelope.py
- 2026-06-11 [claude]: Edit prune_deleted_path.py
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
