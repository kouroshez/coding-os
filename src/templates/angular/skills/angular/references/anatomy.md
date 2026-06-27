<!-- domain:ANGULAR | layer:reference | ssot:true | updated:2026-06-27 -->
# Angular Anatomy

> P: Canonical file map + entity recipes for the Angular (standalone, signals) stack.
> R: Adding any `.ts`/`.html`/`.css` under `src/frontend/`, or routing a frontend task.
> S: Reading backend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/angular/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Component | `src/app/<feature>/<feature>.component.ts` | `<feature>.component.ts` | its service | Standalone, signal-driven view; presentation only |
| Service / state | `src/app/<feature>/<feature>.service.ts` | `<feature>.service.ts` | `HttpClient` | Injectable state (signals) + data access (RxJS) |
| Routes | `src/app/app.routes.ts` | `app.routes.ts` | components | `provideRouter`, lazy `loadComponent` |
| Core | `src/app/core/` | `<name>.ts` | none | Global ErrorHandler, interceptors, guards |
| Bootstrap | `src/main.ts` | `main.ts` | `app.config` | `bootstrapApplication` — no logic |
| Test | `<file>.spec.ts` | `<file>.spec.ts` | source under test | Colocated unit / component spec |

## 3. Entity recipes

### Add a new component
- **Trigger:** "add a `<feature>` view / page".
- **Files emitted:**
  1. `src/app/<feature>/<feature>.component.ts`
  2. `src/app/<feature>/<feature>.component.html`
  3. `src/app/<feature>/<feature>.component.spec.ts`
- **Steps:**
  1. `@Component({standalone: true})`; `inject()` the service.
  2. Read state from `signal()`s; send user intent to the service.
  3. Register a lazy route in `app.routes.ts`.

### Add a new service / state
- **Trigger:** "share state", "call the API".
- **Files emitted:**
  1. `src/app/<feature>/<feature>.service.ts`
  2. `src/app/<feature>/<feature>.service.spec.ts`
- **Steps:**
  1. `@Injectable({providedIn: 'root'})`; hold state in signals.
  2. Data access via `HttpClient`; let the global ErrorHandler shape failures.

### Add a new test
- **Trigger:** any new component / service.
- **Files emitted:** `<file>.spec.ts` next to source.
- **Steps:**
  1. `TestBed.configureTestingModule` with the standalone component.
  2. Assert rendered signal state + service interaction.

## 4. Conventions

#### Naming
- Files: `kebab-case.component.ts`, `kebab-case.service.ts`.
- Classes: `PascalCase` (`UserListComponent`); signals: `camelCase`.

#### Test colocation
- Colocated: `user.component.spec.ts` sits next to `user.component.ts`.

#### Dependency rules
- ✓ component → service → `HttpClient`.
- ✗ component never calls `HttpClient` directly.
- ✗ `src/frontend/` never imports from `src/backend/` / `src/mobile/` — share via `src/shared/`.
