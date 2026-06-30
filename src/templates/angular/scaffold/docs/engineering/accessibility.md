<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-30 -->
# Accessibility (a11y) Checklist — WCAG 2.2 AA (Angular)

Purpose: Living checklist for accessibility compliance across the Angular frontend.
Read when: Building or reviewing any component, route, form, or interactive widget.
Skip when: Working on backend-only tasks.
Read next: [Angular Engineering Rules](./angular-rules.md) for general conventions.

> Nav: [Docs Index](../00-index.md) | [Angular Rules](./angular-rules.md)

---

## Semantics & Interactive Elements

- Prefer native elements (`<button>`, `<a href>`, `<input>`) over `<div (click)>` — they ship roles, focus, and keyboard handling for free.
- Icon-only controls MUST set `[attr.aria-label]` describing the action, not the icon.
- Every form control MUST have an associated `<label for>` (or `aria-label` / `aria-labelledby`).
- Required fields set `[attr.aria-required]="true"`; invalid fields set `[attr.aria-invalid]="true"` and link the message via `[attr.aria-describedby]`.
- Custom widgets (dialog, menu, tabs, combobox) follow the matching ARIA Authoring Practices pattern — reach for `@angular/cdk/a11y` before hand-rolling roles and key handling.

## Keyboard Navigation

- Tab order follows reading order — never `tabindex > 0`.
- Every interactive element is operable with Enter/Space; Escape closes overlays.
- Trap focus inside open dialogs with the CDK `cdkTrapFocus` directive; restore focus to the trigger element on close.
- Keep a visible focus indicator on every focusable element (`:focus-visible`) — never `outline: none` without a replacement.
- The first focusable element of the shell is a "skip to main content" link.

## Dynamic Content

- Announce async state changes (toasts, validation, route changes) with the CDK `LiveAnnouncer` or an `aria-live` region — `polite` for status, `assertive` for errors.
- On client-side navigation, move focus to the new view's `<h1>` so screen-reader users are not stranded on the old page.

## Color & Motion

- Contrast: normal text ≥ 4.5:1; large text (≥ 18.66px bold or ≥ 24px) ≥ 3:1; UI components and focus indicators ≥ 3:1.
- Never convey meaning by color alone — pair it with text or an icon.
- Honor `prefers-reduced-motion`: gate non-essential animation behind the media query.

## Verify

- Static: enable the `@angular-eslint` template-accessibility rules in the lint config.
- Runtime: run axe-core (e.g. `@axe-core/playwright`) against key routes in CI and fail the build on violations.
- Manual: tab through each new view with no mouse, then do a screen-reader pass (VoiceOver / NVDA) on forms and dialogs.

See the core `a11y` skill for cross-framework rationale and screen-reader testing recipes.
