<!-- domain:GO | layer:asset | ssot:false | updated:2026-06-04 -->
# Fiber Review Checklist

Run when writing or reviewing a Fiber v3 handler/app.

## Handlers & errors
- [ ] Handlers return `error`; no inline error responses — central `ErrorHandler` formats the envelope.
- [ ] `fiber.NewError(status, msg)` for client errors; wrap server errors with context.
- [ ] Request context passed down (`c.Context()`) to services/queries.

## Binding & validation
- [ ] Body bound via `c.Bind().Body(&dto)` then validated (go-playground/validator).
- [ ] DTOs separate from domain types; never trust raw input.

## Middleware order
- [ ] `recover` first → requestid → logger → cors → auth (on protected group).
- [ ] Auth on a route group, not duplicated per handler.

## fasthttp gotchas
- [ ] No reference to `c` or its byte slices retained after the handler returns (copy what you keep).
- [ ] `BodyLimit`, `ReadTimeout`, `WriteTimeout` set; large bodies streamed.

## Verify
- [ ] `go test -race ./...` clean; table-driven handler tests (httptest).
- [ ] `golangci-lint`/`go vet` clean.
- [ ] `make skills-check-versions` — Fiber/Go pins current.
