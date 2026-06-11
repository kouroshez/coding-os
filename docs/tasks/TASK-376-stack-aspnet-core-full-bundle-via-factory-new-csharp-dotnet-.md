---
id: TASK-376
title: "Stack: aspnet-core \u2014 full bundle via factory (new csharp/dotnet skill)"
swimlane: templates
kind: feature
epic: D-catalog
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-361]
blocked_by: []
references: []
---

# TASK-376: Stack: aspnet-core — full bundle via factory (new csharp/dotnet skill)

**Outcome (one sentence):** Complete aspnet-core stack bundle including a new csharp/dotnet skill (language=csharp) passing the factory lint — first .NET enterprise coverage.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/go-plain/stack.yaml (plain-language pattern)
- docs/engineering/project-anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the language layer, **When** `csharp-plain` + `aspnet-core` stacks load, **Then** bare "csharp" resolves to csharp-plain and aspnet-core declares language=csharp.
- **Given** the factory contract, **When** `cos init --template aspnet-core --yes --no-index --no-register` runs, **Then** scaffold lands under structure.root with a dotnet-project skeleton and resolved placeholders.
- **Given** the new csharp/dotnet SKILL.md, **When** the skill registry loads, **Then** schema-valid frontmatter with no warnings.
- **Given** the matrix, **When** `uv run pytest tests/test_template_scaffold.py tests/test_anatomy_contract.py -q` runs, **Then** green including golden fixtures.

## Work Log
