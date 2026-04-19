---
globs: ["frontend/**/*.{ts,tsx,css}", "frontend/**/*.js"]
alwaysApply: false
---

# Next.js Frontend Rules (auto-loaded on frontend/**)

When editing any file under `frontend/`, follow these standards:

- **Server Components by default** — add `"use client"` only when you need state, effects, or browser APIs.
- **Typed data boundaries** — every fetch uses a zod schema or explicit type; no `any`.
- **Accessibility** — semantic HTML, labelled inputs, keyboard-reachable interactions.
- **No layout shift** — fixed dimensions on images, reserved space for async content.
- **Colocated tests** — `Component.tsx` + `Component.test.tsx` side by side.

Canonical policy: `docs/engineering/frontend-rules.md`
Playbook: `docs/playbooks/frontend-ui.md`
Primary skill: `nextjs-react`
