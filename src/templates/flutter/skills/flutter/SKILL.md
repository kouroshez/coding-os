---
name: flutter
tier: stack
domain: [mobile]
description: Use when creating or modifying Dart files under src/mobile/ in a Flutter app — screens, widgets, Riverpod providers/notifiers, services, navigation, and their tests. Triggers on any .dart change under src/mobile/. Covers the widget→provider→service layering, the single declarative router, three-state AsyncValue UI, the one error mapper, const-rebuild discipline, Semantics-based a11y, and provider/widget testing. Dart language fundamentals live in clean-code; generic UI in frontend-fundamentals.
globs: "src/mobile/**/*.dart"
depends_on:
  - clean-code
  - frontend-fundamentals
  - a11y
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow `clean-code` (naming, structure, error paths), `frontend-fundamentals` (three-state async UI), and `a11y` (screen-reader semantics). This skill adds Flutter-specific patterns on top.

Anatomy reference: [`references/anatomy.md`](references/anatomy.md). Read that file BEFORE writing any new screen / widget / provider.

# flutter

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `screens/` (ConsumerWidget) | the feature provider, widgets | services, other screens |
| `state/` (provider / notifier) | services, other providers | Flutter `widgets`/`material`, `BuildContext` |
| `services/` | HTTP client, storage, platform channels | providers, widgets |
| `widgets/` | the data + callbacks passed in | services, providers it does not render |
| `core/` (error mapper, router, theme) | providers (for routing guards) | services |

State stays widget-free — a notifier never imports `BuildContext` — so it is
unit-testable and a transport swap (REST → GraphQL → local DB) is a
service-layer-only change.

## State & DI

- One feature = one provider file (`health_provider.dart`) exposing the service
  binding plus the `AsyncValue` the screen watches.
- `ProviderScope` is mounted once in `main.dart`; tests override it per case.
- Inject services through a `Provider`; never `HealthService()` inside `build()`
  — that bypasses overrides and breaks testing.
- Prefer `FutureProvider` / `AsyncNotifier` for async data — the `AsyncValue`
  carries loading/error/data so the screen cannot forget a state.

## Widgets (dumb)

- A screen `watch`es a provider → renders `value.when(loading, error, data)` →
  emits intents via callbacks. No business logic in `build()`.
- Extract reusable presentational pieces into `widgets/`; they take data in and
  call back out, owning no transport.
- `const` constructor wherever the widget allows — it is the cheapest rebuild win.

## Navigation

- ONE declarative router in `core/router.dart` (`go_router`). Widgets navigate by
  name/path through the router; never `Navigator.push(MaterialPageRoute(...))`
  from deep in the tree.

## Error handling

- ONE error mapper (`core/error_mapper.dart`) turns a thrown failure into the
  message a screen shows; it logs full detail and returns a safe string —
  unknown errors get a generic message, never a stack trace or transport string.

## Accessibility

- Wrap interactive widgets in `Semantics` (label + button/header role);
  icon-only buttons carry a `tooltip`. Read tokens from `Theme.of(context)`,
  never literal colours / spacing.

## Testing

- Providers/notifiers: unit tests via a `ProviderContainer`, override the service
  with a fake — no widgets.
- Screens/widgets: `pumpWidget` inside a `ProviderScope` with overridden
  providers, asserting the loading + error + data frames minimum.
- Never bind a real network call in a widget test; inject a fake service.
