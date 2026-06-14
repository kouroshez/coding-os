---
globs: ["src/frontend/**/*.{ts,html,css}"]
alwaysApply: false
---

# Angular Frontend Rules (auto-loaded on src/frontend/**)

When editing any file under `src/frontend/`, follow these standards:

- **Standalone components only** — no NgModules; declare `imports` on the component.
- **Signals for state** — `signal` / `computed` over manual change detection; prefer `OnPush`.
- **Services own side effects** — components stay presentation-only; data + RxJS live in injectable services.
- **Typed data boundaries** — every HTTP response is typed; no `any`.
- **Accessibility** — semantic HTML, labelled inputs, keyboard-reachable interactions.
- **One error shaper** — a global `ErrorHandler` formats errors; components never show raw server messages.

Canonical policy: `docs/engineering/angular-rules.md`
Playbook: `docs/playbooks/angular-app.md`
Primary skill: `angular`
