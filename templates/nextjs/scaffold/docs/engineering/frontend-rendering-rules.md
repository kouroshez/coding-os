<!-- domain:ALL | layer:policy | ssot:true | updated:2026-03-16 -->
# Frontend Rendering Rules

Purpose: Canonical server-first rendering, data-fetching, performance, and testing policy for the frontend.
Read when: A task affects rendering strategy, data access, caching, or test scope.
Skip when: You only need dependency or styling rules.
Read next: `frontend-rules.md` for the broader frontend guardrails.

> Nav: [Frontend Rules](./frontend-rules.md) | [Docs Index](../00-index.md)

## 4) Rendering & Data Strategy (Server-First)

Prefer:

- Server Components for pages, layouts, and data fetching.
- Route-level UX files: `loading.tsx`, `error.tsx`, and `not-found.tsx`.
- `Suspense` boundaries for streaming where beneficial.
- Server Actions for mutations and form submissions.
- A data-access layer in `@/lib/server/data-access.ts`.
- React 19 hooks like `use()` and `useOptimistic()` where appropriate.
- URL search params for filter/pagination state instead of unnecessary client state.

### 4.1 API Client Architecture

**Server-Side Client (`lib/api/server.ts`)** — Server Components & Route Handlers.
Reads JWT from `cookies()`, forwards as `Authorization: Bearer`. Base URL: `BACKEND_INTERNAL_URL` (Docker internal). Error handling: 401 → redirect `/login`, 403 → throw `ForbiddenError`, 404 → `notFound()`, 5xx → throw `ServerError`. Generic typed responses: `apiGet<T>(path)`, `apiPost<T>(path, body)`. No CSRF (server-to-server).

**Client-Side Client (`lib/api/client.ts`)** — Client Components (`'use client'`).
Browser sends JWT via httpOnly cookie (`credentials: 'include'`). Base URL: relative (`/api/v1/...`). CSRF: read `csrftoken` cookie → send as `X-CSRFToken` on mutating methods. Token refresh: on 401 → `POST /api/v1/auth/token/refresh/` → retry once → else redirect `/login`. Rate limit (429): exponential backoff (1s, 2s, 4s), max 3 retries. Timeout: 10s default, 30s uploads.

**Shared Error Handler (`lib/api/errors.ts`)** — Parses API error format per `docs/api-contracts/error-format.md`. Maps to i18n user-friendly messages. Toast for recoverable (400, 422), redirect for auth (401, 403), PostHog `api_error` for 5xx.

**SSE Client (`lib/sse/useEventStream.ts`)** — React hook wrapping `EventSource`. Auto-reconnect; fallback to polling after 5 consecutive failures. Auth via `withCredentials: true`. Ref: `docs/architecture/11-realtime-sse.md`.

**Type Safety** — API response types from backend OpenAPI schema (future: `/api/v1/schema/`); until then manually in `lib/api/types.ts` matching `docs/api-contracts/shared-types-contract.md`. All API functions return typed responses. Never expose Django or Stripe secrets to client bundle.

### 4.2 Client Component Rules

Avoid unless necessary: `'use client'` at page/layout level, `useEffect` for primary data fetching, global client state for server-derived data.

When client components are required: keep them small and isolated, pass server-fetched data down, wrap expensive UI in lightweight suspense boundaries, use `next/dynamic` only when client-only loading is required.

### 4.3 Rendering Strategy Matrix

| Page Type | Strategy | Implementation | Revalidation |
| :------------------- | :-------- | :------------------------------------ | :------------ |
| **Home** | ISR | `export const revalidate = 3600` | 1 hour |
| **Product LP** | ISR | `export const revalidate = 3600` | 1 hour |
| **Products Catalog** | ISR | `export const revalidate = 1800` | 30 min |
| **Blog Posts** | SSG + ISR | `generateStaticParams()` + revalidate | On publish |
| **Blog Hub** | ISR | `export const revalidate = 1800` | 30 min |
| **Cart** | SSR | `dynamic = 'force-dynamic'` | Every request |
| **Checkout** | SSR | `dynamic = 'force-dynamic'` | Every request |
| **Account Pages** | SSR | Cookie-based auth required | Every request |
| **Admin Pages** | SSR | Protected, real-time data | Every request |
| **Legal Pages** | SSG | Build-time only | On deploy |
| **404 / Error** | SSG | Build-time only | On deploy |

### 4.4 Rendering Implementation Patterns

- **ISR** (marketing pages): Set `export const revalidate = <seconds>` at route level. Use `generateStaticParams()` for dynamic slugs.
- **SSR** (dynamic/protected pages): Set `export const dynamic = 'force-dynamic'`. Fetch authenticated data in the server component, pass to client views.
- **SSG** (static legal pages): Plain component export, no data fetching. Rebuilt on deploy only.
- **On-demand revalidation**: Call `revalidatePath()` or `revalidateTag()` inside Server Actions after mutations.

## 5) Performance & Robustness

- Minimize client bundle size and isolate `'use client'`.
- Optimize images through `next/image` with explicit `sizes` and good formats.
- Choose caching/revalidation strategy deliberately.
- Wrap external calls in `try/catch`; handle timeouts, null data, and permission edges.
- Handle errors per rendering strategy: SSR pages show `error.tsx`, ISR pages show stale-while-revalidate fallback, client fetches show inline error with retry.
- Null/undefined data from API must be guarded — use optional chaining and nullish coalescing, never trust API response shape.
- If proposing optimization, include a measurement plan such as Lighthouse or bundle analysis.

## 6) Testing (Only Where It Pays)

- Add unit tests for critical or fragile logic.
- Do not add trivial tests for static markup.
- Prioritize checkout, auth, entitlement, and other security-relevant flows.
