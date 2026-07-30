---
id: TASK-644
title: "aspnet-core bootability blocker \u2014 `dotnet test` fails on fresh init (no test project in scaffold)"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [aspnet-core, bootability, drift, wave-1, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-644: aspnet-core bootability blocker — `dotnet test` fails on fresh init (no test project in scaffold)

**Outcome (one sentence):** A fresh `cos init --template aspnet-core` produces a tree where `cd src/backend && dotnet test` discovers a dedicated xUnit test project with ≥1 passing test and exits 0 — so `make verify` is green on day one instead of failing red on an empty Web-SDK project.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/aspnet-core/scaffold/src/backend/Backend.csproj

## Repro Steps
1. `cos init --template aspnet-core /tmp/x && cd /tmp/x`
2. `cd src/backend && dotnet test`
Expected: at least one test is discovered and the command exits 0.
Actual: `Backend.csproj` is a `Microsoft.NET.Sdk.Web` project with no test-framework deps and the scaffold ships no test project, so `dotnet test` reports "no test is available to run" and `make verify` fails red on a fresh tree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a scaffolded aspnet-core backend, **When** `cd src/backend && dotnet test` runs, **Then** it discovers ≥1 test project and exits 0 (no "no test is available to run").
- **Given** the edited scaffold, **When** `uv run cos stack-lint aspnet-core` runs, **Then** it still PASSES with no new hard failure.
- **Given** the template suite, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** it is green.

## Work Log
- 2026-06-30 [claude]: Edit Backend.sln
- 2026-06-30 [claude]: Edit Backend.Tests.csproj
- 2026-06-30 [claude]: Edit HealthServiceTests.cs
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Backend.sln+xUnit test project+HealthService test; verify→.sln; stack-lint PASS, scaffold 83 passed; dotnet test not…
- 2026-06-30 [claude]: commit b5481aa3e7 — fix(templates): ship aspnet-core xUnit test project for green dotnet test on init
