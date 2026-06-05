---
id: TASK-134
title: "Cross-cutting product docs in base — payments, admin-panel, privacy/terms templates (highest-risk surfaces)"
swimlane: templates
kind: docs
epic: doc-system
labels: [docs-system, templates, payments, policy, audit-d2-f9, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-134: Cross-cutting product docs in base — payments, admin-panel, privacy/terms templates (highest-risk surfaces)

**Outcome (one sentence):** The highest-risk product surfaces get a doc home in _base (they cross stacks): playbooks/payments.md (PCI scope, webhook idempotency, Stripe vs RevenueCat, refund/dunning), engineering/admin-panel.md (RBAC, audit-log, impersonation), governance/{privacy-policy,terms-of-service}.md fill-in templates beside gdpr-compliance.md. Also fix the django dangling pointer to architecture/08-payment-architecture.md / PAYMENTS domain (D2-F9). Reuse auth-patterns + security-web skill content.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/templates/_base/scaffold/docs/governance/gdpr-compliance.md
- src/templates/django/scaffold/docs/

## Work Log
