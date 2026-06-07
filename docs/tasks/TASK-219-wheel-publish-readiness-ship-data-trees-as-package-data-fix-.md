---
id: TASK-219
title: "Wheel publish-readiness: ship data trees as package-data + fix runtime resource resolution so a pip-installed cos finds its files"
swimlane: infra
kind: chore
epic: null
labels: [packaging, release, follow-up-TASK-218, pre-publish-gate]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-07
started: null
completed: null
agent_session: null
depends_on: [TASK-218]
blocked_by: []
references: []
---

# TASK-219: Wheel publish-readiness: ship data trees as package-data + fix runtime resource resolution so a pip-installed cos finds its files

**Outcome (one sentence):** A pip/pipx/uvx-installed cos is fully functional: the non-Python data trees (core/commands .md, core/hooks .sh, core/skills, core/rules, templates, adapters) ship in the wheel via package-data/MANIFEST, AND runtime resource resolution (CODING_OS_ROOT = Path(__file__).parent.parent.parent across ~10 CLI sites) is replaced with importlib.resources or equivalent so the installed cos finds them — verified by installing the wheel into a clean venv and running cos init. Required before TASK-077's first real PyPI publish.

## Work Log
