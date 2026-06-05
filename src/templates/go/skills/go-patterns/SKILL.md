---
name: go-patterns
description: Use when creating or modifying Go files under src/backend/ — HTTP handlers, services, stdlib net/http or chi routers, context propagation, and table-driven tests. Triggers on any .go file change under src/backend/. Covers idiomatic Go, error wrapping, context handling, and concurrency patterns.
globs: "src/backend/**/*.go"
depends_on:
  - clean-code
  - backend-fundamentals
last_reviewed: "2026-06-04"
versions_ref: versions.json

---

REQUIRED BACKGROUND: You MUST also follow the clean-code skill (`.claude/skills/clean-code/SKILL.md`). That skill covers universal principles (fail-closed errors, self-documenting code, edge cases, error path tests). This skill adds Go-specific patterns on top.

## Pre-Code Checklist

- [ ] Read `docs/engineering/go-rules.md` — canonical backend policy
- [ ] If touching HTTP handlers: read `docs/playbooks/go-service.md`
- [ ] Confirm Go version (≥ 1.22 recommended for range-over-func)
- [ ] Search the repo with Grep/Glob for existing code before creating a new file

## 1. Project layout

```
src/backend/
├── cmd/<app>/main.go        # entry point, wire dependencies
├── internal/
│   ├── http/                # handlers, middleware
│   ├── service/             # business logic (no net/http types)
│   ├── repo/                # data access
│   └── model/               # domain types
└── pkg/                     # optional: packages intended for external reuse
```

## 2. Error handling

- Return errors, don't panic. Panic is for programming errors, not runtime conditions.
- Wrap with `fmt.Errorf("operation: %w", err)` to preserve the chain.
- Define sentinel errors for the domain: `var ErrNotFound = errors.New("not found")`.
- Check with `errors.Is` / `errors.As`, never with string matching.

## 3. Context

- First argument of every function that crosses a service boundary: `ctx context.Context`.
- Never store context in struct fields.
- Propagate cancellation through service → repo → DB driver.

## 4. Concurrency

- Goroutines need a clear owner and a way to stop. No fire-and-forget unless the lifetime is the process.
- Use `sync.WaitGroup` + `context.Context` cancellation, or `errgroup.Group`.
- Channels ≠ shared memory. Prefer simple mutex + struct when the data is small and fast.

## 5. Testing

- Table-driven tests. Subtests via `t.Run(tc.name, ...)`.
- `testing.T.TempDir()` for filesystem fixtures.
- Race detector in CI: `go test -race ./...`.
- Coverage target: ≥ 80%.

## Deepening + tooling

- [references/go-2026-idioms.md](references/go-2026-idioms.md) — errors, naming, concurrency, generics, tests (per Google's Go Style Guide).
- [references/anatomy.md](references/anatomy.md) — file map + scaffold; `scripts/new_endpoint.py` to generate one.
- [assets/go-checklist.md](assets/go-checklist.md) — the review gate.
- Versions pinned in [versions.json](versions.json) — `make skills-check-versions`.
