---
id: TASK-603
title: "language config bundle: go, rust, ruby, php, dart, dotnet, jvm lint/format/test config"
swimlane: templates
kind: feature
epic: stack-factory-v2
labels: []
status: icebox
priority: P2
appetite: 2d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: [TASK-598]
blocked_by: []
references: []
---

# TASK-603: language config bundle: go, rust, ruby, php, dart, dotnet, jvm lint/format/test config

**Outcome (one sentence):** Per-language config bundles for the remaining families so every `make lint`/`make test` runs a project-specific configured tool: go (.golangci.yml), rust (rustfmt.toml+clippy), ruby (.rubocop.yml+.rspec), php (pint.json+phpcs.xml+phpstan.neon), dart (analysis_options.yaml), dotnet (.editorconfig rules), jvm (spotless). Honest framing: backend default-linters already catch some bugs — these add project-specific rules, not lint-from-zero.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/go-fiber/stack.yaml
- src/templates/rust-axum/stack.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a go/rust/ruby/php/dart/dotnet/jvm stack, **When** the bundle is applied, **Then** scaffold ships the canonical config for that language's linter + formatter + test runner.
**Given** a verify command that names a linter (e.g. go-fiber golangci-lint), **When** run on a fresh scaffold, **Then** the linter has a backing config and runs with defined linter selection.
**Then** `uv run pytest tests/test_template_scaffold.py -q` is green and the `cos stack-lint` lint-config SOFT-check passes for these stacks.

## Work Log
