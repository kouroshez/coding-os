<!-- domain:ALL | layer:policy | ssot:ref | updated:2026-03-16 -->
# Frontend Engineering Rules

Purpose: Routing hub for frontend implementation policy, dependency discipline, code style, and rendering rules.
Read when: A frontend task needs canonical engineering guidance.
Skip when: A narrower frontend sub-file already answers the question.
Read next: This file for core guardrails, then `frontend-rendering-rules.md` for rendering/data strategy.

> Nav: [Docs Index](../00-index.md) | [Code Style](../../CodeStyle.md) | [STYLE_GUIDE](../../STYLE_GUIDE.md)

## 1) Non-Negotiables (Frontend)

- Follow requirements exactly; if details are missing, log assumptions and choose safe defaults.
- Output complete working code: no TODOs, placeholders, or missing edge cases.
- Prefer readability and correctness over cleverness.
- Use strict TypeScript everywhere; avoid `any`.
- Prefer Server Components and SSR/streaming; isolate `'use client'`.
- Always include loading, error, and empty states.
- Use semantic HTML and accessible interactions.
- Styling: Tailwind only unless the task explicitly requires custom CSS.
- Validate inputs with Zod and never leak secrets.
- New greenfield apps use `create-next-app` with TypeScript and Tailwind.

### Mandatory Engineering Rules

- **Money** → use integer cents only
- **Truth** → webhooks are the source of truth for payments and entitlements
- **Idempotency** → payment and webhook handlers must be idempotent
- **Secrets** → never expose backend or Stripe secrets to the browser
- **Cookie security** → `httpOnly`, `secure` in production, `sameSite: strict`
- **Dynamic settings** → operational toggles belong in DB-backed `site_settings`

## 2) Dependency Discipline

Before adding a library: explain need, list built-in alternative, confirm RSC/SSR compat, check redundancy, keep count minimal. Use the MCP server for shadcn/ui component operations; plan with higher-level blocks before atoms.

### Dependency Selection by Category

| Purpose | Recommended | Why | Avoid |
| ----------------- | --------------------- | ----------------------------------- | ---------------- |
| **UI Components** | shadcn/ui v3 + Radix | Copy-paste, no lock-in | MUI, Chakra |
| **Form Ops** | React Hook Form + Zod | Minimal, best DX | Formik |
| **Auth** | Django + allauth headless (ADR-019) | API-first, built-in JWT | NextAuth |
| **Date** | date-fns / Day.js | Modular, lightweight | moment.js |
| **Icons** | Iconify (Solar) | PRD standard | Font Awesome |
| **Animation** | Framer Motion | PRD standard | jQuery, GSAP |
| **Editor** | Tiptap | Headless, ProseMirror-based | Quill, Draft.js |
| **Captcha** | react-turnstile | Privacy-friendly | ReCaptcha |

## 3) Code Style & Tailwind

- Functional, declarative TypeScript; avoid classes. Use guard clauses and early returns.
- Prefer `const fn = () => {}`; type explicitly when it improves clarity.
- Organize imports: React/Next → third-party → internal → utils/types.
- Avoid unnecessary abstractions; components should have a single clear responsibility.
- Mobile-first responsive layout. Avoid ternaries inside `className`; use a `cn()` helper.
- Keep UI consistent via shadcn/ui components and design tokens.
- Primary CTAs must remain prominent, accessible, and mobile-friendly.
- Prefer logical properties for RTL compatibility.
- Use RGB CSS variables from `globals.css` so Tailwind opacity modifiers work.
- Sort classes as layout → box-model → typography → visuals → misc.
- Shared UI must stay reusable and composable.
- For mission-critical layout components (header, footer, nav): use explicit CSS classes in `globals.css` with raw media queries, not only Tailwind responsive classes — avoids silent breakage from config drift.

## 4) Comments

- Comment **why**, not **what**. If the code is self-evident, no comment is needed.
- Use `TODO: TASK-###` with a task number. Bare TODOs without a task reference are not allowed.
- Comment non-obvious logic, security constraints, and rendering boundary decisions (e.g. `// 'use client' — needs useState for accordion`).
- Do not add JSDoc that restates the component name or props type.

## 5) Auth Middleware Pattern

Auth middleware and token refresh: see `frontend-rendering-rules.md` § 4.1.

## 6) Error Handling

- Every async operation must handle loading, error, and empty states explicitly.
- Use Error Boundaries at route level minimum (`error.tsx` per route group).
- Map API `error_code` to i18n key: `errors.<domain>.<ERROR_CODE>` — never show raw server messages.
- Provide retry action for recoverable errors (network, timeout).
- Use toast for transient errors, inline display for form validation errors.
- Network errors: show retry button, not just "error occurred".
- Never let a failed API call result in a blank screen — always show fallback UI.

## 7) Edge Case Testing

- Test network failure scenarios (API returns 500, timeout, no response).
- Test empty states (no data, empty arrays, null responses).
- Test loading states (verify skeleton/spinner shows before data arrives).
- Test form validation with invalid input, empty required fields, boundary values.
- Test race conditions: rapid navigation, double-click submit, stale data after navigation.
- Never write a test that asserts "renders without crashing" — assert visible content or behavior.

## 8) E2E Testing (Playwright)

E2E tests live in `frontend/e2e/` and are split into two layers:

### Test Pyramid

**UI Tests** (`e2e/ui/`) — no backend needed:

- Page loads, form rendering, navigation, responsive layout
- Run with: `make test-frontend`
- Always pass regardless of backend state
- Use `waitUntil: 'domcontentloaded'` for navigation

**Integration Tests** (`e2e/integration/`) — backend REQUIRED:

- Real API calls verified with `page.waitForResponse()`
- HTTP status asserted (`expect(response.status()).toBeLessThan(400)`)
- Use `requireBackend()` — tests FAIL (not skip) when backend is down
- Run with: `make test-frontend-integration`

### When to write which type

- **UI test**: page loads correctly, form fields render, client-side validation, navigation links work
- **Integration test**: form submit hits API and gets 200, data appears after action, redirect after auth

### Patterns

- Use `waitUntil: 'domcontentloaded'` for navigation — never `'load'` or `'networkidle'`.
- Use `requireBackend()` in integration tests — never `skipIfNoBackend()` or `backendAvailable` branching.
- Use `page.waitForResponse()` to intercept and verify API responses.
- Use `generateTestEmail()` for unique test data per run.
- Prefer `page.getByRole()` and `page.locator('#id')` over fragile CSS selectors.
- Tests must pass without Stripe keys or Turnstile — these are env-var gated.
- Use `attachPageDiagnostics()` to capture console errors, network failures, API calls.

### Network Guard (MANDATORY for integration tests)

**Every integration test MUST use `attachNetworkGuard()`** — a test that passes while the Network tab has errors is a lying test.

```typescript
import { attachNetworkGuard } from '../helpers';

test('my integration test', async ({ page }) => {
  const guard = attachNetworkGuard(page);

  // ... test actions ...

  // MUST be the last assertion — fails if unexpected network errors occurred
  guard.assertNoUnexpectedErrors();
});
```

**How it works:**

- Monitors ALL network responses (4xx, 5xx) and request failures (CSP, timeouts, aborts)
- Compares against a whitelist of expected errors (e.g., guest 401 on `/api/auth/user`)
- Fails with a detailed report showing exactly which requests failed

**To whitelist test-specific expected errors:**

```typescript
const guard = attachNetworkGuard(page, [
  { urlPattern: /\/api\/v1\/some-endpoint/, status: 404 },
]);
```

**Default whitelist** (always allowed):

- `GET /api/auth/user` — guest users always get 401, this is expected
- `lh3.googleusercontent.com` CSP — Google-hosted images blocked by CSP in dev
- `/_next/image` 400 — missing local images in dev mode

### Running

- `make test-frontend` — UI tests only (no backend)
- `make test-frontend-integration` — integration tests (backend required)
- `make test-frontend-headed` — visible browser
- `make ci-gate` — full pipeline: lint → backend → UI → integration → diagnose

## Sub-File Routing

- [frontend-rendering-rules.md](./frontend-rendering-rules.md)
  Server-first rendering strategy, API client boundaries, performance, and testing guidance.

## Quick Routing

- Dependency choice or package fit → this file
- Shared component style or Tailwind rule → this file
- Server vs client rendering, SSR/ISR/SSG, caching, or tests → `frontend-rendering-rules.md`
