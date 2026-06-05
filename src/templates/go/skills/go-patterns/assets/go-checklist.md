<!-- domain:GO | layer:asset | ssot:false | updated:2026-06-04 -->
# Go Review Checklist

Run when writing or reviewing Go.

## Errors
- [ ] Errors wrapped with `%w` + context at each layer; checked via `errors.Is`/`As`.
- [ ] Error strings lowercase, no trailing punctuation.
- [ ] No `panic` for ordinary errors; `panic` only for truly unrecoverable state.

## Naming & API
- [ ] No stutter (`user.New`, not `user.NewUser`).
- [ ] Accept interfaces, return concrete types; one-method interfaces `-er`-named.
- [ ] Exported identifiers have a doc comment starting with the name.

## Concurrency
- [ ] `context.Context` is the first arg of any call that does I/O or can block.
- [ ] Every goroutine has a clear stop condition (ctx / channel close).
- [ ] Shared state guarded (mutex/channel); `go test -race` clean.
- [ ] `errgroup` for bounded concurrent work with error collection.

## Generics & structure
- [ ] Generics only where ≥2 instantiations remove real duplication.
- [ ] cmd/ internal/ pkg/ layout respected (see anatomy.md).

## Tests & tooling
- [ ] Table-driven subtests (`t.Run`), `require`/`assert` (testify), `t.Parallel()` where safe.
- [ ] `gofmt`/`goimports` clean; `golangci-lint` clean; `go vet` clean.
- [ ] `make skills-check-versions` — Go/testify pins current.
