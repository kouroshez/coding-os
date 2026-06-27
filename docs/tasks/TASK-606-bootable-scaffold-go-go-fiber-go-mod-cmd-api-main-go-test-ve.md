---
id: TASK-606
title: "bootable scaffold: go + go-fiber (go.mod + cmd/api/main.go + test + verify block)"
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
depends_on: [TASK-603]
blocked_by: []
references: []
---

# TASK-606: bootable scaffold: go + go-fiber (go.mod + cmd/api/main.go + test + verify block)

**Outcome (one sentence):** go and go-fiber become runnable seeds (today scaffold/src/backend = .gitkeep only — verified P0, `go test`/`go vet` fail). Each gets go.mod (go-fiber: fiber v3 + validator) + cmd/api/main.go with graceful shutdown + a *_test.go pulling the T5 (TASK-603) .golangci.yml, plus the missing `verify:` block.

## Read First
- src/templates/go/stack.yaml
- src/templates/go-fiber/stack.yaml
- src/templates/go-fiber/skills/go-fiber/versions.json

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** go, **When** `cos init` then `make lint-go`/`make test-go`, **Then** they pass on a go.mod + cmd/api/main.go + a *_test.go (today both fail — no go.mod).
**Given** go-fiber, **When** the same, **Then** go.mod pins fiber v3 + validator, the generated handler compiles, and golangci-lint runs against the shipped .golangci.yml.
**Given** both stacks, **Then** the `verify:` per-glob block is present in stack.yaml.
**Then** `uv run pytest tests/test_template_scaffold.py -q` is green.

## Work Log
