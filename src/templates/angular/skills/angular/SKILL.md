---
name: angular
tier: stack
domain: [frontend]
description: Use when creating or modifying TypeScript/HTML/CSS files under src/frontend/ in an Angular SPA — standalone components, injectable services, signals, RxJS streams, routes, guards, interceptors, and their tests. Triggers on any .ts/.html change under src/frontend/. Covers standalone bootstrap, signal-driven change detection, service-owned state and side effects, the global ErrorHandler, and component testing with TestBed. Stack-agnostic UI patterns live in the core frontend-fundamentals skill.
globs: "src/frontend/**/*.{ts,html}"
depends_on:
  - clean-code
  - frontend-fundamentals
  - a11y
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `frontend-fundamentals` skill (stack-agnostic UI patterns — three-state async, accessibility, SEO), `a11y`, and `clean-code`. This skill adds ONLY Angular-specific patterns on top.

# angular

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `*.component.ts` | feature service, child components, signals | `HttpClient`, shared mutable state, sibling services' internals |
| `*.service.ts` | `HttpClient`, other services, RxJS | `@Component` APIs, the DOM, components |
| `core/` (error handler, guards, interceptors) | services (for auth/config lookups) | feature components |
| `app.config.ts` / `app.routes.ts` | providers, route targets | business logic |

Components stay presentation-only — no `HttpClient`, no shared mutable state — so
they are testable in isolation and a data-source swap is a service-layer-only
change.

## Standalone & bootstrap

- Every component is `standalone: true` and declares its own `imports`. No
  `@NgModule` anywhere in this stack.
- The app boots via `bootstrapApplication(AppComponent, appConfig)` in `main.ts`
  (no logic). Application-wide providers live in `app.config.ts` — the DI root.
- Routes are a flat `Routes` array in `app.routes.ts`; lazy-load non-trivial
  features with `loadComponent`.

## State & change detection

- Drive the view with `signal`/`computed`/`effect`; pair every component with
  `ChangeDetectionStrategy.OnPush`.
- A service owns shared/global state via signals exposed as `asReadonly()`; the
  component reads them and never mutates global state directly.
- Pass data in with typed `input()`, changes out with `output()`; no two-way
  mutation of shared state from a child. Manual `detectChanges()` in feature
  code signals a missing signal.

## Services & DI

- Data access and side effects live in `@Injectable({ providedIn: "root" })`
  services using `HttpClient` + RxJS — never in a component.
- Inject with `inject()` or constructor params; never `new` a service — that
  bypasses the injector and breaks test overrides.
- Surface config through a typed service; never read globals (`window`,
  `import.meta.env`) deep inside a component.

## Error handling

- ONE global `ErrorHandler` (`core/global-error-handler.ts`) logs full detail.
  The UI shows a generic, mapped message — never a raw server/stack string.
  Map API error codes to user-facing i18n keys at the display boundary.

## RxJS & teardown

- Prefer the `async` pipe in the template over manual `subscribe`.
- A manually-subscribed stream MUST tear down via `takeUntilDestroyed()` (or an
  explicit `Subscription` cleared in the destroy hook) — an unmanaged
  subscription leaks.

## Testing

- Services: pure unit tests — exercise signals/streams with stubbed `HttpClient`,
  no DOM.
- Components/e2e: `TestBed.configureTestingModule({...})` then render and assert
  one interaction, one happy + one error path per feature minimum.
- Never depend on real network or timers; provide stubs through the testing
  injector.
