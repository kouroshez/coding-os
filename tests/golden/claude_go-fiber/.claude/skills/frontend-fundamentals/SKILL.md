---
name: frontend-fundamentals
tier: layer
domain: [frontend, mobile]
description: Stack-agnostic frontend patterns. Use when writing or modifying any UI code (React, React Native, Vue, Svelte) regardless of framework. Covers three-state async UI, loading/error/empty handling, client vs server components, hydration safety, accessibility, performance, SEO basics, and state management patterns.
globs: "frontend/**/*"
paths: ["frontend/**/*"]
context: fork
depends_on:
  - clean-code
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
last_reviewed: "2026-05-11"

---

# Frontend Fundamentals — Stack-Agnostic UI Patterns

Universal guidance for every component-based UI framework: React, React Native, Vue, Svelte, Solid. Framework-specific layering (Next.js App Router, React Native navigation, Vue composition API) lives in the stack-specific skill that `depends_on: [frontend-fundamentals]`.

Loaded automatically when `enforce-skill.sh` routes a file under `frontend/` that matches a stack skill.

## 0. Every async UI is three-state

Every screen or section that fetches data MUST explicitly handle three states. Missing any of them is a bug:

| State | Required UI |
|---|---|
| **Loading** | skeleton or spinner; indication of progress |
| **Error** | actionable message + retry affordance; never a blank screen |
| **Empty** | explains why it's empty + suggests next action; never an ambiguous zero rows |

A fourth state — **stale/refreshing while data exists** — is a common polish item. Render the previous data with a subtle loading indicator; don't blank the UI.

Anti-pattern: `{data && <List data={data} />}`. This silently hides error AND empty AND loading behind a single falsy check.

## 1. Server components vs. client components (React 19+ / Next 15+)

Default everything to server components. Convert to client only when one of these is present:

- **Interactive state** (`useState`, `useReducer`, form state).
- **Event handlers** (`onClick`, `onChange`, `onSubmit`).
- **Browser-only APIs** (`window`, `localStorage`, `navigator`, `document`, `IntersectionObserver`).
- **Hooks that require a client** (`useEffect`, `useLayoutEffect`, most third-party hooks).

Server components don't ship JS to the browser and can fetch directly. This is the single biggest first-load perf win in modern React. A component that's `"use client"` without a reason is accidental bundle bloat.

## 2. Hydration safety

Anything whose output differs between the first server render and the first client render causes a hydration mismatch. Common culprits:

- `new Date()`, `Math.random()` at top level of a client component.
- `window.matchMedia(...)` defaulting to different value.
- Reading `localStorage` synchronously during render.

Fix: move non-deterministic values to `useEffect` + `useState`, render the deterministic initial value during SSR, swap after mount. For `localStorage`-backed state, guard with `typeof window !== "undefined"` AND initialize via effect to avoid SSR/CSR drift.

## 3. Loading / error / empty component contract

Build a shared tri-state component once per project:

```tsx
<AsyncBoundary
  isLoading={query.isLoading}
  error={query.error}
  isEmpty={query.data?.length === 0}
  onRetry={query.refetch}
  emptyCTA={<CreateFirstItemButton />}
>
  <List items={query.data} />
</AsyncBoundary>
```

Forces callers to think about all three states. A `null` / `undefined` passed for `isEmpty` is a linter error, not a silent skip.

## 4. Error boundaries — at every major route

- One error boundary per route segment. Never a single root boundary (a crashed card shouldn't white-screen the whole app).
- Error boundary UI: explain what happened + "Try again" button + "Contact support" link. Never just "Something went wrong."
- Log the error to the telemetry backend (Sentry, PostHog, custom endpoint) with the component tree context.
- Error boundaries DON'T catch: async errors inside `useEffect`, event handler errors, errors in server components on a separate request. Handle those with try/catch + explicit state.

## 5. Accessibility — the minimum floor

- **Every interactive thing has a label.** Buttons have text or `aria-label`; form inputs have `<label htmlFor>`; icons that act as buttons have `aria-label`.
- **Keyboard navigable.** Tab reaches every focusable element, Enter/Space activates, Escape closes. Custom dropdowns/modals/menus must trap focus when open and restore on close.
- **Visible focus ring.** Never `outline: none` without replacing it. Focus ring is legally required in many jurisdictions.
- **Semantic HTML first.** `<button>` not `<div onClick>`. `<nav>`, `<main>`, `<article>`, `<section>` not `<div>` soup. Heading order (h1→h2→h3) doesn't skip.
- **Alt text on every `<img>`.** Decorative → `alt=""`. Informative → describe the content.
- **Color contrast ≥ 4.5:1** for normal text (AA). Test with browser DevTools contrast checker; don't eyeball.

Use `axe-core` / `eslint-plugin-jsx-a11y` in CI. Manual keyboard-only walkthrough of the happy path before every release.

## 6. Performance — the non-negotiables

- **Lazy-load route-level code splits.** Every route is a dynamic import boundary.
- **Lazy-load below-the-fold components** (modals, carousels, rare tabs).
- **Images: width + height always, `loading="lazy"` for below-fold, responsive `srcset` for above-fold hero.**
- **Memoize expensive derivations**, NOT every `useCallback`. Memoization has a cost — use it when the dependency array is stable AND the downstream comparison is expensive.
- **Virtualize lists > 100 items** (`react-window`, `tanstack/virtual`). Rendering 1000 DOM nodes makes scroll jank on mobile.
- **Target Core Web Vitals**: LCP < 2.5 s, INP < 200 ms, CLS < 0.1. Measure on real devices, not local Chrome on fiber.

## 7. State management — smallest scope that works

Default to component-local `useState`. Promote up the tree ONLY when:

- Two siblings need the same state → lift to closest common parent.
- Many distant components need it → global store (Zustand / Jotai / Redux Toolkit / Pinia).
- Server data → use a data-fetching library (TanStack Query / SWR / RTK Query). **Never** store server data in a client store manually; it invites stale-data bugs.

Separate three kinds of state:

1. **Server state** (cached from backend) — TanStack Query / SWR.
2. **URL state** (what's selected, active tab, filters) — query params (survives refresh + shareable).
3. **Client-only UI state** (dropdown open, hovered item) — local `useState`.

Mixing these in one store is the origin of 80 % of "why is the UI wrong after a refresh" bugs.

## 8. Form handling

- **Controlled inputs** for anything with validation or dependent logic.
- **Validate client + server.** Client for UX (fast feedback), server as the authority. The server's validation schema IS the contract.
- **Disable submit while submitting.** Re-clicking a submit button during the request is one of the most common double-submit bugs.
- **Show field-level errors inline** next to the input, not a single toast at the top.
- **Announce errors to screen readers** (`aria-live="polite"`).

Libraries: `react-hook-form` + `zod` / `yup`; `formik`; `vee-validate` for Vue. All handle the boring parts (dirty/touched, field-level errors) correctly.

## 9. SEO basics (web, not mobile)

For every page that should be indexable:

- **Unique `<title>`** — includes page name + brand, < 60 chars.
- **`<meta name="description">`** — unique per page, 140–160 chars.
- **Open Graph** (`og:title`, `og:description`, `og:image`, `og:url`) — the social-share preview.
- **Twitter Card** — `twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`.
- **Canonical URL** — `<link rel="canonical">` pointing at the locale-specific version. Do NOT share canonicals across locales.
- **Structured data (JSON-LD)** for product / article / breadcrumb / FAQ pages — `<script type="application/ld+json">`.
- **Semantic HTML** helps crawlers (see §5).

## 10. i18n — if the app ships in > 1 language

- **One string catalog per locale** (`en.json`, `fa.json`, ...). No hardcoded UI strings in components.
- **Pluralization** via ICU MessageFormat or framework built-in (`Intl.PluralRules`).
- **RTL support** for Arabic / Hebrew / Persian — use logical CSS properties (`margin-inline-start` not `margin-left`).
- **Locale-aware formatting** for dates, numbers, currencies (`Intl.DateTimeFormat`, `Intl.NumberFormat`).
- **URL structure** — `/` default + `/<locale>/` for additional locales. Ship `<html lang>` and `<link rel="alternate" hreflang>`.

## 11. localStorage / sessionStorage — SSR-safe

```tsx
// WRONG — crashes on SSR and hydration
const [theme, setTheme] = useState(localStorage.getItem("theme") ?? "light");

// RIGHT — deterministic initial render, swap after mount
const [theme, setTheme] = useState<"light" | "dark">("light");
useEffect(() => {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") setTheme(stored);
}, []);
```

Never access `window` / `localStorage` / `document` at module top level or during render of a component that might SSR. Pattern: initialize with a deterministic default, swap inside an effect.

## 12. Mobile-first (React Native + responsive web)

- **Design for touch.** Min tap target 44×44 px (iOS HIG) / 48 dp (Material).
- **Respect safe areas.** Use `SafeAreaView` (React Native) / `env(safe-area-inset-top)` (web). Content under the notch is a bug.
- **Offline-first** for mobile networks. Cache read-heavy data, queue writes, reconcile on reconnect.
- **Optimistic UI** for write actions when a rollback path is cheap. Show the action as done immediately; reconcile if the server rejects.

## 13. Testing — the minimum coverage

- **Unit test components with behavior.** Render + assert interaction outcomes (`testing-library/react`, `@testing-library/react-native`). Test from the user's perspective, not implementation (role / text, not class names).
- **Three-state test per async component.** Render while loading, resolved with data, resolved empty, rejected — each is a separate test.
- **E2E happy path** on the 3–5 critical flows (login, checkout, main CRUD). Playwright / Cypress / Detox.
- **Snapshot tests sparingly.** They're easy to write and hard to trust; prefer explicit assertions.

## 14. Pre-commit / PR checklist

Before opening a PR touching a frontend file:

- [ ] Server component unless something forces `"use client"`
- [ ] Loading / error / empty states all explicitly rendered
- [ ] Error boundary at route level
- [ ] Keyboard-only nav works end-to-end (tab + enter + escape)
- [ ] Focus-visible ring present on all interactive elements
- [ ] Images have `width`/`height` + `alt`
- [ ] Form validates client-side AND server-side
- [ ] No top-level `localStorage` / `window` access in components that SSR
- [ ] `<title>` + `<meta description>` + canonical per indexable page
- [ ] Core Web Vitals not regressed (LCP / INP / CLS checked in DevTools)

## References

Stack-specific specializations extend this skill via `depends_on: [frontend-fundamentals]`:

- [src/templates/nextjs/skills/nextjs-react/SKILL.md](../../../templates/nextjs/skills/nextjs-react/SKILL.md)
- [src/templates/nextjs/skills/frontend-design/SKILL.md](../../../templates/nextjs/skills/frontend-design/SKILL.md)
- future: `src/templates/react-native/skills/react-native/SKILL.md`

Universal principles from [clean-code](../clean-code/SKILL.md) still apply — this skill does not relax any of them.
