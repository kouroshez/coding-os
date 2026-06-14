<!-- domain:MOBILE | layer:rules | ssot:true | updated:{{DATE}} -->
# Flutter Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Flutter app.
Read when: Editing anything under `src/mobile/`.
Skip when: Frontend/backend work.
Read next: [Flutter App Playbook](../playbooks/flutter-app.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — widget → provider → service, imports flow one way only (the
   table in the `flutter` skill is the SSOT). A widget never imports a service.
2. **Dumb widgets** — a widget renders state and emits intents; any logic in a
   `build()` method is a review finding. Business logic lives in a notifier.
3. **One error shaper** — only `lib/core/error_mapper.dart` turns a thrown
   failure into UI state; it logs full detail and surfaces a safe message — no
   stack traces, no driver strings to the user.
4. **Three-state fail-closed** — every async screen renders loading / error /
   empty / data explicitly via `AsyncValue.when`; a missing branch ships a frame
   of blank or jank.
5. **State discipline** — shared state goes through a Riverpod provider injected
   by `ProviderScope`; `setState` is reserved for ephemeral single-widget UI.
6. **Strict analysis** — `dart analyze` with `flutter_lints` is the gate; an
   ignore comment requires a written justification at the site.
7. **No floating config** — environment access happens once at bootstrap;
   providers receive typed config, never read `Platform.environment` directly.

## Testing bar

Providers / notifiers ≥ unit-tested per public method with a `ProviderContainer`;
screens ≥ loading + error + data path via `pumpWidget` with overridden providers;
services integration-tested against a fake transport. Never bind a real network
call in a widget test.
