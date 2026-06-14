<!-- domain:FRONTEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Angular Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Angular frontend.
Read when: Editing anything under `src/frontend/`.
Skip when: Backend/mobile work.
Read next: [Angular App Playbook](../playbooks/angular-app.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Standalone only** — `standalone: true` on every component; no `@NgModule`.
   Declare per-component `imports`; the layering table in the `angular` skill is
   the SSOT.
2. **Signals for state** — `signal`/`computed`/`effect` drive the view; pair
   with `ChangeDetectionStrategy.OnPush`. Manual `ChangeDetectorRef.detectChanges`
   in feature code is a review finding.
3. **Services own side effects** — a component importing `HttpClient` or holding
   shared mutable state is a build-blocking finding; that belongs in an
   injectable service.
4. **One error shaper** — only the global `ErrorHandler` logs full detail; the UI
   shows a generic, mapped message — never a raw server/stack string.
5. **Dependency injection** — inject with `inject()` or constructor params;
   never `new` a service — it bypasses the injector and breaks test overrides.
6. **Strict TypeScript + templates** — `tsc --noEmit` with `strictTemplates` is
   the lint gate; `any` requires a written justification at the site.
7. **Unsubscribe discipline** — prefer the `async` pipe or `takeUntilDestroyed`;
   a manually-subscribed stream without teardown leaks.

## Testing bar

Services ≥ unit-tested per public method (signals, no DOM); components ≥ render +
one interaction via `TestBed`, happy + error path; guards/interceptors tested in
isolation against a stubbed `HttpClient`.
