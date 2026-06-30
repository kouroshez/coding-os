<!-- domain:FRONTEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Angular App Playbook

Purpose: The end-to-end recipe for adding or changing an Angular feature in {{PROJECT_NAME}}.
Read when: Any task that adds a component, service, route, guard, or interceptor.
Skip when: Backend/mobile work — see the relevant stack docs.
Read next: [Angular Engineering Rules](../engineering/angular-rules.md), [Accessibility](../engineering/accessibility.md)

> Nav: [Master Index](../00-index.md)

## Add a feature (the only sanctioned path)

1. **Component** — `src/frontend/src/app/<feature>/<feature>.component.ts`:
   standalone, `ChangeDetectionStrategy.OnPush`, declares its own `imports`.
   Presentation only — it reads signals and emits events.
2. **Service** — `<feature>.service.ts`: `@Injectable({ providedIn: "root" })`,
   owns state via `signal`/`computed` and side effects via RxJS + `HttpClient`.
   The component never fetches or mutates global state directly.
3. **Route** — register the component in `app.routes.ts`; lazy-load with
   `loadComponent` once the feature is non-trivial.
4. **Guard / interceptor** — cross-cutting concerns live under `core/` and are
   provided in `app.config.ts`, never inline in a component.
5. **Inputs/outputs** — pass data in with typed `input()`, signal changes out
   with `output()`; no two-way mutation of shared state from a child.
6. **Test** — unit-test the service in isolation (signals, no DOM) +
   component test via `TestBed` (render + interaction, happy + error path).
7. **Verify** — `cd src/frontend && npm run lint && npm test`.

## Global wiring (set once in `app.config.ts`)

`provideRouter → provideHttpClient → { provide: ErrorHandler, useClass:
GlobalErrorHandler }`. Application-wide providers live here so every component
inherits routing, HTTP, and one error shape.

## Anti-patterns

- An NgModule (`@NgModule`) — this stack is standalone-only.
- A component calling `HttpClient` directly — data access belongs in a service.
- `setTimeout`/manual change detection to "force" a refresh — drive the view
  from a `signal`/`computed` instead.
- Formatting a raw server error string into the template — the global
  `ErrorHandler` owns logging; the UI shows a generic, mapped message.
