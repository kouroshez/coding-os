---
globs: ["src/backend/**/*.go"]
alwaysApply: false
---

# Fiber Backend Rules (auto-loaded on src/backend/**/*.go)

When editing any Go file under `src/backend/` in a Fiber project, follow these standards:

- **Handler signature** — `func(c *fiber.Ctx) error`. Return `c.Status(code).JSON(payload)` or a concrete error.
- **Typed errors** — wrap with `fmt.Errorf("…: %w", err)`. At the top level, convert via a centralized error-handler middleware that emits `{"error": {"code", "message", "details"}}`.
- **Context** — always pass `c.UserContext()` (or `c.Context()`) into downstream DB / HTTP calls so cancellation propagates.
- **Validation** — use `go-playground/validator` on request structs; handler returns 422 with field-level details on failure. No bare `c.BodyParser` without validate.
- **Middleware order** — recover → requestid → logger → cors → compress → auth → route group. Never put business logic in middleware.
- **Table-driven tests** — every handler gets `httptest.NewRequest` + `app.Test()` coverage, happy + error paths. No reflection-heavy mocks.
- **Separation** — routes/, handlers/, services/, repositories/, models/. Handlers don't talk to DB directly — services do.

Canonical policy: `docs/engineering/fiber-rules.md`
Playbook: `docs/playbooks/fiber-service.md`
Primary skill: `go-fiber`
