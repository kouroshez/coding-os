---
id: TASK-479
title: "Community-stack/adapter FILE application from source_dir (scaffold copy + skill linker + config composer) \u2014 make overlay stacks usable end-to-end"
swimlane: infra
kind: feature
epic: null
labels: [modularity, plugins, audit-pass4, review-fix, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-479: Community-stack/adapter FILE application from source_dir (scaffold copy + skill linker + config composer) — make overlay stacks usable end-to-end

**Outcome (one sentence):** TASK-471 wired community-stack DISCOVERY into consumer commands, but the file-APPLICATION machinery still reconstructs bundled paths (TEMPLATES_DIR/name) instead of the resolved StackProfile.source_dir — so a discovered community stack scaffolds zero files, links no skills, and composes no .coding-os config (silent half-apply). This task makes init/add-stack honor profile.source_dir so an out-of-tree stack is usable end-to-end.

## Read First
- src/cli/main.py
- src/cli/stack_registry.py
- src/core/scripts/link-stack-skills.sh
- src/cli/config_composer.py
- docs/playbooks/template-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a valid community stack at $COS_USER_TEMPLATES_DIR/acme/ with scaffold/ + skills/ **When** cos init --template acme / cos add-stack acme run **Then** _overlay_scaffold copies acme's scaffold from profile.source_dir (not TEMPLATES_DIR/acme) — **And** stack skills link from source_dir (the link-stack-skills.sh interface accepts the resolved per-stack skills dir, or a Python-side fallback links community skills) — **And** config_composer reads the community stack's .coding-os contributions from source_dir — **And** the SSOT regen/lint paths stay bundled-only — **And** a test asserts a monkeypatched community stack's scaffold file lands in the project. Depends on the TASK-471 discovery wiring (already landed).

## Work Log
