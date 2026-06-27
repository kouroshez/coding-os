<!-- domain:FLUTTER | layer:reference | ssot:true | updated:2026-06-27 -->
# Flutter Anatomy

> P: Canonical file map + entity recipes for the Flutter (Riverpod, declarative-router) stack.
> R: Adding any `.dart` under `src/mobile/`, or routing a mobile task.
> S: Reading backend / web code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/flutter/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Screen | `lib/screens/<feature>_screen.dart` | `<feature>_screen.dart` | state, widgets | One widget tree per route (`ConsumerWidget`) |
| Widget | `lib/widgets/<name>.dart` | `<name>.dart` | — | Reusable presentational component |
| State | `lib/state/<feature>_provider.dart` | `<feature>_provider.dart` | services | Riverpod provider / notifier — business logic |
| Service | `lib/services/<name>_service.dart` | `<name>_service.dart` | `http` | Transport + platform access |
| Core | `lib/core/` | `<name>.dart` | none | Error mapper, router, theme |
| Test | `test/<file>_test.dart` | `<file>_test.dart` | source under test | `flutter_test` |

## 3. Entity recipes

### Add a new screen
- **Trigger:** "add a `<feature>` screen / route".
- **Files emitted:**
  1. `lib/screens/<feature>_screen.dart`
  2. `lib/state/<feature>_provider.dart`
  3. `test/<feature>_screen_test.dart`
- **Steps:**
  1. `ConsumerWidget`; watch the provider, render from its state.
  2. Send user intent to the notifier; never hold business logic in the widget.
  3. Register the route in the declarative router (`lib/core/`).

### Add a new component
- **Trigger:** "extract a reusable widget".
- **Files emitted:** `lib/widgets/<name>.dart` (+ test).
- **Steps:**
  1. Stateless + parameterized; no provider reads — pass data in.

### Add a new test
- **Trigger:** any new screen / widget / provider.
- **Files emitted:** `test/<file>_test.dart`.
- **Steps:**
  1. `ProviderContainer` for state; `testWidgets` + `pumpWidget` for UI.

## 4. Conventions

#### Naming
- Files: `snake_case.dart`. Classes: `PascalCase`; members: `camelCase`.

#### Test colocation
- Mirrored: `test/<file>_test.dart` mirrors `lib/<file>.dart`.

#### Dependency rules
- ✓ screen → state → service.
- ✗ a widget never turns a failure into UI text — the one core error mapper does.
- ✗ `src/mobile/` never imports from `src/frontend/` / `src/backend/` — share via `src/shared/`.
