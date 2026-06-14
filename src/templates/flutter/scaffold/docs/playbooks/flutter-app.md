<!-- domain:MOBILE | layer:playbook | ssot:true | updated:{{DATE}} -->
# Flutter App Playbook

Purpose: The end-to-end recipe for adding or changing a screen, widget, or provider in {{PROJECT_NAME}}.
Read when: Any task that adds a screen, reusable widget, Riverpod provider, route, or service.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [Flutter Engineering Rules](../engineering/flutter-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add a screen (the only sanctioned path)

1. **State first** — model the screen's data as an immutable value and expose it
   from a provider in `lib/state/<feature>_provider.dart`. Async data uses
   `AsyncValue` so loading / error / data fall out of the type.
2. **Service** — `lib/services/<feature>_service.dart` owns transport (HTTP /
   storage / platform channel). It returns domain values or throws a typed
   failure; it never touches widgets.
3. **Screen** — `lib/screens/<feature>_screen.dart`: a `ConsumerWidget` that
   `watch`es the provider and renders `value.when(loading, error, data)`. No
   business logic in `build()`.
4. **Widgets** — extract reusable presentational pieces into `lib/widgets/`;
   they take data in and emit callbacks, holding no provider reads of their own
   beyond what they render.
5. **Route** — register the screen in the single declarative router
   (`lib/core/router.dart`); never push raw `MaterialPageRoute` from a widget.
6. **Error mapping** — failures surface through `lib/core/error_mapper.dart`,
   which converts a thrown failure into the `AsyncError` the screen renders.
7. **Test** — widget-test the screen's three states via `pumpWidget` with a
   `ProviderScope` override; unit-test the provider/notifier in isolation.
8. **Verify** — `cd src/mobile && dart analyze && flutter test`.

## Global wiring (set once in `main.dart`)

`runApp` mounts a single `ProviderScope` over a `MaterialApp.router` bound to the
declarative router. Theme + error mapper are wired here so every screen inherits
one token set and one failure shape.

## Anti-patterns

- Business logic inside `build()` — it belongs in a provider / notifier.
- A widget calling a service directly — go through a provider so it stays testable.
- `try/catch` building an error message in a screen — the error mapper owns it.
- `Navigator.push(MaterialPageRoute(...))` from deep in a widget — route through
  the declarative router instead.
