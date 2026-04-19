# Go Service Playbook

Project: {{PROJECT_NAME}} · Stack: {{STACK}} · Updated: {{DATE}}

## When to use

Any task that creates, modifies, or debugs HTTP handlers, services, or domain
code under `backend/` in a Go module.

## Always read

1. `docs/engineering/go-rules.md` — canonical backend policy
2. This file — routing and layout conventions

## Task-to-file mapping

| Task type | Files to read first |
|---|---|
| New HTTP endpoint | `backend/internal/http/<resource>.go`, related service |
| New service method | `backend/internal/service/<domain>.go`, related repo |
| Repository change | `backend/internal/repo/<resource>.go`, DB schema |
| Concurrency | `backend/internal/service/*.go` — watch for shared state |

## Execution rules

1. Handlers never touch the DB directly — always via a service method.
2. Context is the first argument of every cross-boundary call.
3. Errors flow up wrapped with `%w`; top-level handler maps them to HTTP codes.
4. Every new handler gets a table-driven test covering happy + error paths.
5. Run `make lint-go && make test-go` before marking task-done.
