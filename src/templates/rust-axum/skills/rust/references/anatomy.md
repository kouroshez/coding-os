<!-- domain:RUSTAXUM | layer:reference | ssot:true | updated:2026-06-27 -->
# Rust + Axum Anatomy

> P: Canonical file map + entity recipes for the Rust + Axum (tokio, tower, AppError) stack.
> R: Adding any `.rs` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/rust-axum/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Handler | `src/routes/<domain>.rs` | `<domain>.rs` | service, error | Thin async fn → `Result<Json<_>, AppError>` |
| Router | `src/app.rs` | `app.rs` | routes | Route table + tower middleware layers |
| Error | `src/error.rs` | `error.rs` | none | The ONE `AppError` → `IntoResponse` shaper |
| Entry | `src/main.rs` | `main.rs` | `app` | tokio entry; binds the listener — no logic |
| Module index | `src/routes/mod.rs` | `mod.rs` | route files | Re-exports the domain handlers |
| Test | `#[cfg(test)]` / `tests/<name>.rs` | `<name>.rs` | source under test | `tokio::test` + `tower::ServiceExt` |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `GET /<domain>`".
- **Files emitted:**
  1. `src/routes/<domain>.rs`
  2. registration in `src/routes/mod.rs` + `src/app.rs`
- **Steps:**
  1. Handler is an async fn with extractors (validate fail-closed) → `Result<_, AppError>`.
  2. Return `Ok(Json(..))` or an `AppError`; never write a response body inline.
  3. Layer the route into the router in `app.rs`.

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:** `src/<domain>/model.rs` (+ repository).
- **Steps:**
  1. Plain struct + `serde`; DB access behind a repository, not the handler.

### Add a new test
- **Trigger:** any new handler.
- **Files emitted:** `#[cfg(test)] mod tests` or `tests/<name>.rs`.
- **Steps:**
  1. Drive the router via `app.oneshot(request)`; assert status + body.

## 4. Conventions

#### Naming
- Files / modules: `snake_case.rs`. Types: `PascalCase`; fns: `snake_case`.

#### Test colocation
- Colocated: `#[cfg(test)] mod tests` in the source file; integration in `tests/`.

#### Dependency rules
- ✓ handler → service → repository; errors flow up as `AppError`.
- ✗ no `.unwrap()` on fallible paths in a handler — return `AppError`.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
