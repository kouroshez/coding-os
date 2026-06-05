<!-- domain:GO | layer:reference | ssot:true | updated:2026-06-04 -->
# Fiber v3 Patterns (2026)

> P: Build Fiber v3 handlers/middleware correctly — routing, binding, validation, errors.
> R: Writing or reviewing a Fiber handler, middleware, or app setup.
> S: General Go idioms — see the go-patterns skill's go-2026-idioms reference.
> N: [SKILL.md](../SKILL.md), [fiber-checklist.md](../assets/fiber-checklist.md)

> Nav: [Skill](../SKILL.md)

Fiber v3 (GA Feb 2026) requires Go 1.25+. Some v2 signatures changed — check
[versions.json](../versions.json) and the migration notes when porting.

## Handler + error model

```go
app.Get("/users/:id", func(c fiber.Ctx) error {     // v3: fiber.Ctx (interface), return error
    id, err := c.ParamsInt("id")
    if err != nil {
        return fiber.NewError(fiber.StatusBadRequest, "invalid id")
    }
    u, err := svc.Get(c.Context(), id)               // pass the request context down
    if err != nil {
        return err                                    // central error handler formats it
    }
    return c.JSON(u)
})
```

Handlers return `error` — don't write error responses inline; return a
`fiber.NewError(status, msg)` (or a wrapped error) and let a **central error
handler** render the envelope consistently:

```go
app := fiber.New(fiber.Config{
    ErrorHandler: func(c fiber.Ctx, err error) error {
        code := fiber.StatusInternalServerError
        var fe *fiber.Error
        if errors.As(err, &fe) { code = fe.Code }
        return c.Status(code).JSON(fiber.Map{"error": fiber.Map{"message": err.Error()}})
    },
})
```

## Binding + validation

```go
type CreateUser struct {
    Email string `json:"email" validate:"required,email"`
    Name  string `json:"name"  validate:"required,min=2"`
}

func create(c fiber.Ctx) error {
    var body CreateUser
    if err := c.Bind().Body(&body); err != nil {      // v3 binding API
        return fiber.NewError(fiber.StatusBadRequest, "bad body")
    }
    if err := validate.Struct(body); err != nil {     // go-playground/validator
        return fiber.NewError(fiber.StatusUnprocessableEntity, err.Error())
    }
    ...
}
```

Bind then validate at the boundary; never trust the body. Keep DTOs separate from
domain types (the api-contract-discipline applied to Fiber).

## Middleware — order matters

```go
app.Use(recover.New())        // catch panics → 500, don't crash the process
app.Use(requestid.New())      // correlation id for logs/traces
app.Use(logger.New())         // structured request log
app.Use(cors.New(corsCfg))    // before auth
// auth middleware AFTER cors, BEFORE protected routes
protected := app.Group("/api", authMiddleware)
```

Recover first (so a panic in any later middleware/handler is caught), then
requestid/logger, then cross-cutting (cors), then auth on the protected group.
Auth is owned by [auth-patterns](../../../core/skills/auth-patterns/SKILL.md);
security review by [security-web](../../../core/skills/security-web/SKILL.md).

## Performance notes

Fiber is fasthttp-based — `fiber.Ctx` and its buffers are **reused across
requests**; never retain a reference to `c` or its byte slices after the handler
returns (copy what you need). Stream large bodies; set sane `BodyLimit`,
`ReadTimeout`, `WriteTimeout` in `fiber.Config`.
