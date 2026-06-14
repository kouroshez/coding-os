---
name: rust
tier: stack
domain: [backend]
description: Use when creating or modifying Rust files under src/backend/ in an Axum service — handlers, the router (app.rs), extractors/DTOs, the central AppError IntoResponse error shaper, tower middleware layers, Arc<AppState> shared state, and their tokio tests. Triggers on any .rs change under src/backend/. Covers thin async handlers returning Result<T, AppError>, ?-propagation over unwrap, fail-closed extractor validation, the single IntoResponse error shaper, and router testing via tower oneshot. Generic backend design lives in backend-fundamentals.
globs: "src/backend/**/*.rs"
depends_on:
  - clean-code
  - backend-fundamentals
  - api-design
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `backend-fundamentals` skill (request lifecycle, layering, idempotency) and `clean-code` (fail-closed errors, self-documenting code, error-path tests). This skill adds ONLY Rust + Axum-specific patterns on top; `api-design` governs the public contract.

# rust

## Layer contract (matches `structure.tree`) — the SSOT for layering

| Layer | May import | Never |
|---|---|---|
| `main.rs` | `app.rs` (the router builder), tokio | handler/business logic |
| `app.rs` | `routes::*`, tower layers, `AppState` | request-specific logic |
| `routes/<domain>.rs` (handlers) | `AppState`, extractors, services, `AppError` | another domain's privates, raw response bodies |
| `error.rs` (`AppError`) | domain error types | handlers, route wiring |

Handlers are thin async fns returning `Result<T, AppError>` — they parse via an
extractor, call one service method, and return the value (Axum serializes). The
business logic survives a transport swap because nothing below the handler imports
an Axum type.

## Handlers (thin) & routing

- A handler signature is `async fn(State<Arc<AppState>>, <Extractor>) -> Result<Json<T>, AppError>`.
  Parse/validate via the extractor → call ONE service method → return `Ok(Json(..))`.
- Never hand-build the response envelope or `match` on errors to build JSON —
  `?`-propagate into `AppError` and let its `IntoResponse` shape the body.
- Routes are assembled in `app.rs` (`Router::new().route(...).with_state(state)`);
  one module per domain under `routes/`, re-exported through `routes/mod.rs`.

## Error handling (the one shaper)

- ONE `AppError` enum in `error.rs` implements `IntoResponse` — it is the ONLY
  place that writes an error body (RFC 9457 problem shape per
  `docs/api-contracts/error-format.md`). Map domain errors into it with
  `thiserror` + `From` so handlers stay `?`-only.
- Unknown/internal errors → 500 with a generic body; full detail goes to the
  `tracing` logger only — never a `Debug`/backtrace or DB message to the client.

## `?` over `.unwrap()` / `.expect()`

- Request paths NEVER `.unwrap()` / `.expect()` — convert with `?` into `AppError`.
  A panic in a handler aborts the task and leaks nothing useful to the client.
- `.unwrap()`/`.expect()` is allowed ONLY at startup (binding the listener, reading
  required config) where a failure SHOULD abort the process before serving traffic.

## Extractors, state & middleware

- Input validation is fail-closed at the extractor boundary: `Json<Dto>` /
  `Query<Dto>` reject malformed input (400) before the handler body runs; a handler
  never reads the raw request.
- Shared state is `Arc<AppState>` injected via `State<Arc<AppState>>` — no global
  mutable statics, no `lazy_static!` request state.
- Tower middleware (`TraceLayer`, timeout, CORS, auth) lives in `app.rs` as
  `.layer(...)` on the router — never inside an individual handler.

## Testing

- `#[tokio::test]` driving the router via `tower::ServiceExt::oneshot(request)` —
  no real port is bound. One happy + one error path per route minimum.
- Services: pure unit tests with fakes, no router. Assert the `AppError` variant on
  the error path, not just the status, so a remap is caught.
- `cargo clippy -- -D warnings` is the lint gate; warnings are errors.
