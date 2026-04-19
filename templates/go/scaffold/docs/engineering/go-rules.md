# Go Engineering Rules

Project: {{PROJECT_NAME}} · Updated: {{DATE}}

## Layout

- `cmd/<app>/main.go` — entry, wiring only.
- `internal/http/` — handlers + middleware.
- `internal/service/` — pure business logic, no `net/http` types.
- `internal/repo/` — data access.
- `internal/model/` — domain types.
- Nothing in `internal/` is importable outside this module — that's the invariant.

## Error handling

- Return, don't panic. Panic is for programming errors.
- Wrap with `%w` to preserve the chain: `fmt.Errorf("create user: %w", err)`.
- Define sentinel errors at package boundaries: `var ErrNotFound = errors.New(...)`.
- Compare with `errors.Is` / `errors.As` only. Never string-match.

## Context

- First argument of every function that crosses a service boundary: `ctx context.Context`.
- Never put context in struct fields.
- Respect `ctx.Done()` — long-running loops must select on it.

## Concurrency

- Goroutine ownership is explicit. Document who stops it.
- `errgroup.Group` for fan-out with shared error semantics.
- Channels for coordination, mutexes for state.
- `-race` in CI is mandatory.

## Testing

- Table-driven tests with subtests via `t.Run`.
- `testing.T.TempDir()` for filesystem.
- Mock at interface boundaries, not function signatures.
- Coverage target: ≥ 80%.

## Tooling

- `gofmt -s` on save.
- `go vet ./...` + `staticcheck` in CI.
- `go test -race -cover ./...` in CI.
