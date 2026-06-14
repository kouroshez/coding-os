<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Rust + Axum Service Playbook

Purpose: The end-to-end recipe for adding or changing an Axum endpoint in {{PROJECT_NAME}}.
Read when: Any task that adds a handler, route, extractor, tower middleware layer, or error variant.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [Rust + Axum Engineering Rules](../engineering/rust-axum-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Contract first** — define the request/response types as `serde` structs;
   error cases map to an `AppError` variant ([error-format](../api-contracts/error-format.md)).
2. **Handler** — `src/backend/src/routes/<feature>.rs`: an async fn that takes
   extractors (`Json<Dto>`, `Path<_>`, `State<_>`) and returns
   `Result<Json<_>, AppError>`. Call one service method, return the value.
3. **Validate at the extractor** — a malformed body is rejected by the
   `Json<Dto>` extractor before the handler body runs; never read the raw request.
4. **Service** — business logic lives in a transport-free module that knows
   nothing about `axum` types; it returns domain `Result`s the handler maps via `?`.
5. **Wire** — register the route in `app.rs`
   (`.route("/<feature>", post(<feature>::create))`).
6. **Error** — propagate with `?`; add a new `AppError` variant + `From` impl if a
   new failure category needs a distinct status. Never build error JSON in a handler.
7. **Test** — `#[tokio::test]` driving the router via `ServiceExt::oneshot`
   (happy + error path), plus pure unit tests on the service.
8. **Verify** — `cd src/backend && cargo clippy -- -D warnings && cargo test`.

## Global wiring (set once in `app.rs` / `main.rs`)

Routes + tower middleware are assembled in `app.rs::router()`; `main.rs` only
builds the tracing subscriber, binds the listener, and calls `axum::serve`. Add
cross-cutting concerns (tracing, timeout, CORS) as `.layer(...)` on the router —
never inside a handler.

## Anti-patterns

- Error JSON built inside a handler — the `AppError` `IntoResponse` impl owns the shape.
- `.unwrap()` / `.expect()` in a request path — propagate with `?`; `unwrap` is for startup only.
- A handler importing the service's DB client directly — keep the service transport-free.
- `.layer(...)` middleware applied per handler — middleware belongs on the router in `app.rs`.
- A global mutable `static` for shared state — use `State<Arc<AppState>>`.
