---
globs: ["backend/**/*.go"]
alwaysApply: false
---

# Go Backend Rules (auto-loaded on backend/**/*.go)

When editing any Go file under `backend/`, follow these standards:

- **Return errors, don't panic.** Panic is for programming errors, not runtime conditions.
- **Wrap errors with `%w`** — `fmt.Errorf("create user: %w", err)`. Compare with `errors.Is` / `errors.As`.
- **Context first** — every cross-boundary function takes `ctx context.Context` as the first argument.
- **No context in struct fields.** Propagate, don't store.
- **Goroutine ownership is explicit** — document who starts and who stops each goroutine.
- **Table-driven tests** with subtests via `t.Run`. `-race` in CI.

Canonical policy: `docs/engineering/go-rules.md`
Playbook: `docs/playbooks/go-service.md`
Primary skill: `go-patterns`
