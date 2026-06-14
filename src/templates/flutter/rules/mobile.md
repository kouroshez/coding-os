<!-- domain:FLUTTER | layer:policy | ssot:true | updated:2026-06-14 -->
# Flutter — stack rules

> P: Compact rule list applied to every `src/mobile/**/*.dart` file in addition to clean-code, frontend-fundamentals, and a11y.
> R: Reviewing or writing any Flutter code.
> S: Touching the web frontend or backend.
> N: [skills/flutter/SKILL.md](../skills/flutter/SKILL.md), [skills/flutter/references/anatomy.md](../skills/flutter/references/anatomy.md)

## Hard rules

1. **Three-state UI.** Every data-fetching screen renders loading / error / empty / content explicitly — `AsyncValue.when` is the canonical switch.
2. **Widgets stay dumb.** A widget renders state and emits intents; business logic lives in a provider / notifier, never in `build()`.
3. **One error mapper.** Only `lib/core/error_mapper.dart` turns a thrown failure into UI state; widgets never `try/catch` to build a message.
4. **No `setState` for shared state.** Cross-screen state goes through a Riverpod provider; `setState` is for ephemeral, single-widget UI only.
5. **a11y on every interactive element.** Wrap actionable widgets in `Semantics` (label + button/header role); icon-only buttons require a `tooltip`.
6. **No hard-coded design tokens.** Read colours / spacing / text styles from `Theme.of(context)`, never literal hex / magic numbers.
7. **`const` constructors by default.** A widget that can be `const` must be — it is the cheapest rebuild win.
8. **Boundary.** May import from `src/shared/`. Never from `src/frontend/`, `src/backend/`, `src/ai-service/`.

## Pre-commit checklist

- [ ] Three-state branches present on every async screen.
- [ ] No business logic inside `build()`.
- [ ] `Semantics` / `tooltip` on every interactive widget.
- [ ] Tokens read from `Theme.of(context)`, no literal colours.
- [ ] `dart analyze` clean (no warnings) and `flutter test` green.
