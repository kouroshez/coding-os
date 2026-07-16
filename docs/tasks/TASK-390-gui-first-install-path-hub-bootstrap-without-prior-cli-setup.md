---
id: TASK-390
title: "GUI-first install path \u2014 Hub bootstrap without prior CLI setup (installer/Docker one-liner)"
swimlane: infra
kind: feature
epic: B-onboarding
labels: [backlog, onboarding-program, ready]
status: archive
priority: P3
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-390: GUI-first install path — Hub bootstrap without prior CLI setup (installer/Docker one-liner)

**Outcome (one sentence):** A user with no cos CLI can boot the Hub via a single installer/Docker command and reach the onboarding wizard; ADR records the trust/path trade-offs.

## Read First
- README.md (current install quickstart)
- docs/engineering/hub-architecture.md
- src/cli/hub.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a machine with only Docker (or bash+curl for the installer script), **When** the documented one-liner runs, **Then** the Hub boots on :9188 and the onboarding wizard is reachable without any prior `uv tool install` step.
- **Given** the installer script, **When** `bash -n` + shellcheck run in CI, **Then** clean; the script verifies prerequisites via `cos doctor --bootstrap` semantics before claiming success.
- **Given** the ADR, **When** `make docs-lint` runs, **Then** green; the ADR records path/trust trade-offs (where the meta-repo lives, how projects mount, auth posture from TASK-363).
- **Given** the matrix, **When** the targeted install-path test (script smoke, mocked network) runs, **Then** green.

## Work Log
- 2026-06-15 [claude]: committed 3396b410: docs/architecture/adr/00-index.md, docs/architecture/adr/0007-gui-first-install-path.md, install.sh,
