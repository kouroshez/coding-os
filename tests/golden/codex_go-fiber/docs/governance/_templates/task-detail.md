---
# Phase L lean task template — see docs/phase-l-scrumban-task-system-plan.md
#
# AGENT: All four categorization axes are required (`epic` optional).
# `validate-task-frontmatter.sh` will reject this file on Write/Edit if any
# enum is wrong, swimlane is unknown, or `labels` overlaps `kind` values.
#
# Prefer creating tasks via `cos_task_create` MCP tool over hand-writing
# this YAML — the tool fills, validates, and persists in one call.
id: {{TASK_ID}}
title: "{{TITLE}}"
swimlane: {{SWIMLANE}}            # DOMAIN — must exist in scrumban-config.yaml::swimlanes
kind: {{KIND}}                    # TYPE — feature | bug | chore | spike | docs | refactor | test | security
epic: {{EPIC|null}}               # INITIATIVE — optional (e.g. phase-l, mvp, oncall-q2)
labels: {{LABELS|[]}}             # FREE TAGS — must NOT contain kind values
priority: {{PRIORITY|P2}}         # P0 critical | P1 high | P2 normal | P3 low
appetite: "{{APPETITE|1d}}"       # Shape Up: 30m | 2h | 1d | 3d | 1w | 1cy
status: icebox                    # always start here; transition via cos_task_move
created: {{TODAY}}
started: null
completed: null
agent_session: null
depends_on: {{DEPENDS_ON|[]}}     # hard block — these must complete first
blocked_by: []                    # runtime block — agent fills with reason
references: {{REFERENCES|[]}}     # soft relationship; sibling tasks
---

# {{TASK_ID}}: {{TITLE}}

**Outcome (one sentence):** <!-- AGENT: ONE concrete sentence describing what
will be true when this task is done. Not a re-spec. Not a goal. A measurable
end-state with metric where possible. Bad: "improve auth". Good: "users log
in with email + OTP, P95 < 500ms, on iOS + Android + web". -->

## Read First
<!-- AGENT: ONLY links to existing docs/files. NEVER inline content from them.
If no relevant doc exists: (a) note "no doc — exploratory", or (b) create
the doc first via Formula 4 then link to it. Rule 15 forbids duplication. -->

- [path/to/doc.md](relative/path) — short reason
- [path/to/code.py](relative/path) — short reason

## Acceptance (G/W/T) — *this IS the Definition of Done*
<!-- AGENT: 1–3 Given/When/Then statements. Each becomes a test case.
When ALL pass, task is Done. Not "perfect" — Done. Scope-creep =
new task via cos_task_create. -->

- **Given** <precondition>
- **When** <action>
- **Then** <observable outcome with concrete metric>

## Work Log
<!-- AGENT: AUTO-APPENDED by capture-work-log.sh hook on Write/Edit.
Format: `- YYYY-MM-DD [agent-id | ses-NNNNNNNN]: <120-char summary>`.
NEVER rewrite. NEVER reformat. Append-only. Codex sessions: call
cos_work_log_append() explicitly (no PostToolUse hook). -->

## Rollback
<!-- AGENT: Optional but recommended. If purely additive: "Additive only.
Revert commit." If has migrations or shared-state mutations: list explicit
undo steps. -->
