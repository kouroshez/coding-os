<!-- domain:ENGINEERING | layer:reference | ssot:true | updated:2026-03-23 -->
# Accessibility (a11y) Checklist — WCAG 2.1 AA

Purpose: Living checklist for accessibility compliance across the frontend.
Read when: Building or reviewing any interactive component.
Skip when: Working on backend-only tasks.
Read next: `./frontend-rules.md` for general frontend conventions.

> Nav: [Docs Index](../00-index.md) | [Frontend Rules](./frontend-rules.md)

---

## Interactive Elements

- All icon-only buttons MUST have `aria-label` describing the action
- All form inputs MUST have associated `<label>` elements (htmlFor + id)
- Required form fields MUST have `aria-required="true"`
- Form validation errors MUST be linked to inputs via `aria-describedby`
- Custom interactive elements (drawers, modals, dropdowns) MUST have `role` attributes
- Modal/drawer close buttons MUST have `aria-label="Close"`

## Dynamic Content

- Toast notifications use Sonner which provides aria-live regions automatically
- Cart count badge changes should be announced via `aria-live="polite"`
- Form error messages should use `aria-live="assertive"`

## Keyboard Navigation

- Tab order follows logical reading order (no `tabindex > 0`)
- All interactive elements activatable via Enter or Space
- Escape closes modals and drawers
- Focus trap active inside open modals
- Visible focus indicator on all interactive elements (`:focus-visible`)

## Color Contrast (WCAG AA)

- Normal text (< 18px): 4.5:1 minimum contrast ratio
- Large text (>= 18px bold or >= 24px): 3:1 minimum contrast ratio
- Interactive elements: 3:1 against adjacent colors
- Focus indicators: 3:1 against background

## Current Status

- 26 files with aria-label attributes
- Sonner toast library provides built-in aria-live support
- shadcn/ui components include keyboard navigation by default
- Cookie consent banner has `role="dialog"` and `aria-label`
- Honeypot field has `aria-hidden="true"` and `tabindex="-1"`

## Remaining Items

- Audit form inputs for missing aria-required on required fields
- Verify Tab order on checkout flow
- Color contrast verification with automated tool (axe-core or Lighthouse)
- Add skip-to-content link at top of page
