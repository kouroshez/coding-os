<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Rust + Axum Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Rust + Axum backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [Rust + Axum Service Playbook](../playbooks/rust-axum-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Thin handlers** — a handler extracts, calls one service method, returns the
   value as `Result<_, AppError>`. Business logic in a handler is a
   build-blocking review finding (the layer table in the `rust` skill is the SSOT).
2. **One error shaper** — only `AppError`'s `IntoResponse` impl writes an error
   body; it logs full detail and returns the problem shape with no internals
   (no panics, no driver messages, no backtraces to the client).
3. **No panics in request paths** — `.unwrap()`/`.expect()`/`panic!` are forbidden
   off the startup path; propagate with `?` and convert via `From`/`thiserror`.
   `unwrap` is acceptable only in `main` where failure should abort the process.
4. **Validation fail-closed** — every input is an extractor-validated `serde`
   DTO; an unvalidated body never reaches a service.
5. **Transport-free services** — the service layer imports no `axum` types so it
   stays unit-testable and a transport swap is a handler-only change.
6. **Shared state via `State<Arc<…>>`** — no global mutable statics; clone the
   `Arc`, never the inner value.
7. **Clippy is the lint gate** — `cargo clippy -- -D warnings` must pass;
   `unsafe` and `#[allow(...)]` require a written justification at the site.

## Testing bar

Services ≥ unit-tested per public method; handlers ≥ happy + error path driven
through the router via `tower::ServiceExt::oneshot` (no bound port); repositories
integration-tested against a disposable database. `cargo test` is the gate.
