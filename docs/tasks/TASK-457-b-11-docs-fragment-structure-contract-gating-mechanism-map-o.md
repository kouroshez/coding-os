---
id: TASK-457
title: "B-11 docs: fragment-structure contract + gating-mechanism map + out-of-tree plugin overlay (MD-3/MD-4)"
swimlane: docs
kind: docs
epic: null
labels: [modularity-audit-pass3, MD-3, MD-4, docs-update, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-457: B-11 docs: fragment-structure contract + gating-mechanism map + out-of-tree plugin overlay (MD-3/MD-4)

**Outcome (one sentence):** template-authoring.md gains a single SSOT for the three things pass-3 found undocumented: (MD-3) a gating-mechanism map — which of the 3 toggle mechanisms (render-time jinja {% if modules.X %}, init-time <!-- if-module / |module: --> doc strip, runtime _gated_module / skill-primer filter) to use for a given intent and why they coexist (different lifecycles); (MD-4) the _base fragment structure contract (one ## heading, no frontmatter/footer, \n\n-joined, empty→skipped, base.yaml order, the {% endif %}{% if %} whitespace-control idiom) — previously only in code comments; and the B-7 out-of-tree community plugin overlay ($COS_USER_TEMPLATES_DIR / $COS_USER_ADAPTERS_DIR, no-shadow rule, fail-soft adapters). Also adds a pass-3 backlog register (B-1..B-11) to the audit SSOT doc.

## Read First
- docs/playbooks/template-authoring.md
- docs/engineering/modularity-audit-2026-06.md
- src/cli/_resources.py

## Work Log
- 2026-06-19 [claude]: Edit template-authoring.md
- 2026-06-19 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-19 [claude]: committed 2d556768 · 2 files
