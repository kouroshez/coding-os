---
globs: ["src/backend/**/*.rs"]
alwaysApply: false
---

# Rust + Axum Backend Rules (auto-loaded on src/backend/**/*.rs)

When editing any Rust file under `src/backend/`, follow these standards:

- **Handlers are thin async fns** returning `Result<T, AppError>` — parse via an extractor, call one service method, return the value. Axum serializes; never hand-build the response envelope.
- **One error shaper** — the central `AppError` (in `error.rs`) implements `IntoResponse`; it is the ONLY place that writes an error body. Handlers `?`-propagate; they never `match` to build error JSON.
- **Errors propagate with `?`, never `.unwrap()`/`.expect()`** in request paths — convert with `From`/`thiserror` into `AppError`. `.unwrap()` is allowed only at startup where a failure should abort the process.
- **Extractors validate fail-closed** — `Json<Dto>`/`Query<Dto>` reject malformed input before the handler body runs; a handler never reads the raw request.
- **Tower middleware lives in `app.rs`** as `.layer(...)` calls on the router — never inside an individual handler.
- **Shared state is `Arc<AppState>`** injected via `State<…>`; no global mutable statics.
- **Tests** — `#[tokio::test]` calling the router via `tower::ServiceExt::oneshot`; one happy + one error path per route minimum.

Canonical policy: `docs/engineering/rust-axum-rules.md`
Playbook: `docs/playbooks/rust-axum-service.md`
Primary skill: `rust`
