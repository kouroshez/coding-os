<!-- domain:GO | layer:reference | ssot:true | updated:2026-06-04 -->
# Go Idioms (2026) — Errors, Naming, Concurrency, Generics

> P: The modern Go idioms (per Google's Go Style Guide) that keep code clear and safe.
> R: Writing or reviewing any Go; deciding error/concurrency/generics style.
> S: The stack file map + scaffold — see [anatomy.md](anatomy.md).
> N: [SKILL.md](../SKILL.md), [go-checklist.md](../assets/go-checklist.md)

> Nav: [Skill](../SKILL.md)

## Errors — wrap with context, check with errors.Is/As

```go
// Wrong — loses the call site; the caller can't tell what failed
if err != nil { return err }

// Correct — wrap with %w so errors.Is/As still work up the stack
if err != nil { return fmt.Errorf("load user %d: %w", id, err) }

// sentinel + typed checks
var ErrNotFound = errors.New("not found")
if errors.Is(err, ErrNotFound) { ... }
var ve *ValidationError
if errors.As(err, &ve) { ... }
```

Add context at each layer (`%w` preserves the chain); never `panic` for ordinary
errors. Error strings are lowercase, no trailing punctuation (they get wrapped).

## Naming — short, scoped, no stutter

- Package names short + lowercase (`http`, `user`); the package qualifies, so
  `user.New()` not `user.NewUser()` (stutter).
- Short names for short scopes (`i`, `r`, `ctx`); descriptive for package-level.
- Interfaces named for behavior (`Reader`, `Stringer`); one-method interfaces take
  the `-er` suffix. Accept interfaces, return concrete types.
- Exported identifiers need a doc comment starting with the name.

## Concurrency — own the lifecycle

```go
// context flows first-arg; cancellation propagates
func fetch(ctx context.Context, id int) (*User, error) { ... }

// bound goroutines + collect errors
g, ctx := errgroup.WithContext(ctx)
for _, u := range urls {
    u := u
    g.Go(func() error { return process(ctx, u) })
}
if err := g.Wait(); err != nil { return err }
```

A goroutine you start, you must be able to stop — pass `ctx`, select on
`ctx.Done()`. Never start a goroutine without knowing how it ends. Protect shared
state with a mutex or a channel; run tests with `-race`. Prefer `errgroup` over
hand-rolled `sync.WaitGroup` + error plumbing.

## Generics — only when they remove real duplication

```go
func Map[T, U any](s []T, f func(T) U) []U {
    r := make([]U, len(s))
    for i, v := range s { r[i] = f(v) }
    return r
}
```

Generics earn their place for container/algorithm code with ≥2 concrete
instantiations. Don't genericize what an `interface` already expresses, and don't
add a type parameter used once. Constrain with `comparable`/`constraints` or a
custom constraint interface.

## Tests — table-driven + testify

```go
func TestDiscount(t *testing.T) {
    tests := []struct{ name string; price, pct, want int }{
        {"ten percent", 100, 10, 90},
        {"zero", 100, 0, 100},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            require.Equal(t, tt.want, discount(tt.price, tt.pct))
        })
    }
}
```

Table-driven subtests with `t.Run` (named cases, parallel-safe); `require` to stop
on a failed precondition, `assert` to continue. `t.Parallel()` for independent
cases. Fuzz (`func FuzzX(f *testing.F)`) for parsers.
