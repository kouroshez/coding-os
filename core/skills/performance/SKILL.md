---
name: performance
description: Application performance for backend (Go+Fiber, Python+FastAPI), web frontends, and React Native mobile clients. Use when measuring or improving Web Vitals (LCP / INP / CLS), mobile FPS / TTI / memory, image/font/code-split optimization, profiling, or interpreting Lighthouse / Reanimated / Hermes / Flipper traces. Pairs with frontend-fundamentals + react-native-patterns + db-design.
---

# Performance — Web + Backend + Mobile

A practical playbook for measuring, profiling, and improving performance across the project's stack. Covers Web Vitals (Google's user-experience metrics), mobile perf budgets (FPS / TTI / memory), backend latency (P95 / P99 / saturation), with concrete tools per surface.

## When to Use This Skill

- Adding a perf budget to a new feature.
- Investigating a Lighthouse / Web Vitals regression.
- Mobile users report jank, slow app launch, battery drain.
- Backend P95 latency exceeds SLO.
- Bundle size jumped 30% after a release.
- Lists scroll poorly; animations stutter.
- Choosing between perf tools (when each pays off).

## The Three Performance Surfaces

| Surface | Primary metrics | Tools |
|---|---|---|
| **Backend** | P50 / P95 / P99 latency, throughput, error rate, saturation (CPU / mem / IO) | OpenTelemetry, Datadog APM, pprof (Go), py-spy (Python), pgbadger (Postgres) |
| **Web frontend** | LCP, INP, CLS (Core Web Vitals), TTI, TBT, bundle size | Lighthouse, Chrome DevTools Performance, WebPageTest, web-vitals JS lib |
| **Mobile** | FPS (60/120), TTI, memory, bundle size, native render time | Flipper, React DevTools Profiler, Hermes Sampling Profiler, Xcode Instruments, Android Profiler, FlashList Recorder |

Each has its own measurement approach; conflate them at your peril.

## Measurement First, Optimization Second

The cardinal rule: don't optimize without numbers. The biggest performance regressions in the wild come from devs "fixing" something that wasn't slow.

**Workflow**:

1. Establish a budget (e.g., LCP < 2.5s P75, list scroll 60 FPS, P95 < 200ms).
2. Measure on real conditions (real device, real network, real data volume).
3. Identify the bottleneck via profiling.
4. Fix the bottleneck.
5. Re-measure to confirm improvement.
6. Pin a regression test if possible (CI bundle-size gate, k6 load test).

## Web Vitals (2026 — current Google ranking signals)

| Metric | What it measures | Good | Needs improvement | Poor |
|---|---|---|---|---|
| **LCP** (Largest Contentful Paint) | Time until largest element renders | ≤ 2.5s | 2.5–4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | Worst interaction latency in session — replaced FID March 2024 | ≤ 200ms | 200–500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | Visual stability over the page lifetime | ≤ 0.1 | 0.1–0.25 | > 0.25 |
| TTFB (Time to First Byte) | Server response start | ≤ 0.8s | 0.8–1.8s | > 1.8s |

Measure on REAL devices via the `web-vitals` library; aggregate at P75 across users (Google's threshold).

```html
<script type="module">
  import { onLCP, onINP, onCLS } from 'https://unpkg.com/web-vitals?module';
  onLCP((metric) => sendToAnalytics('LCP', metric));
  onINP((metric) => sendToAnalytics('INP', metric));
  onCLS((metric) => sendToAnalytics('CLS', metric));
</script>
```

For per-metric optimization tactics (image priorities for LCP, JS chunking for INP, reserved space for CLS), see [references/web-vitals.md](references/web-vitals.md).

## Mobile Perf Budgets

| Metric | Target | Hard fail |
|---|---|---|
| App cold start (TTI) | < 1.5s on mid-tier device | > 3s |
| App warm start | < 500ms | > 1s |
| Frame rate during scroll | 60 FPS (or 120 on ProMotion) | < 50 FPS |
| Frame rate during animation | same | jank visible |
| Memory after 5 min use | < 250MB | > 400MB |
| JS bundle size | < 4MB uncompressed | > 8MB |
| Native size (per platform) | < 50MB download | > 100MB |
| Battery drain (1 hr active use) | < 5% | > 10% |

Measure on a **mid-tier device** (Pixel 6a, iPhone 12 mini), not the top of the line. Real users have older phones.

For RN-specific patterns (Hermes optimizations, FlashList, Reanimated worklets, native module trade-offs, bundle analysis), see [references/mobile-performance.md](references/mobile-performance.md).

## Backend Perf Budgets

| Metric | Target | Hard fail |
|---|---|---|
| P50 latency | < 100ms | > 300ms |
| P95 latency | < 300ms | > 1s |
| P99 latency | < 1s | > 3s |
| Error rate | < 0.1% | > 1% |
| CPU utilization | < 70% sustained | > 90% |
| Memory utilization | < 70% sustained | > 90% |
| DB connection pool usage | < 60% | > 90% |
| Cache hit rate (where applicable) | > 90% | < 70% |

P95 / P99 matter more than P50 — the slow tail is the user experience for the unlucky users.

Per-language tools:

- **Go**: `pprof` for CPU / heap / goroutine profiles. `runtime/trace` for execution traces. `httptrace` to dissect outbound calls.
- **Python**: `py-spy` for sampling profiler. `cProfile` for deterministic. `tracemalloc` for memory leaks. `asyncio` debug mode for slow awaits.
- **Node**: `--prof` + `--prof-process`. Clinic.js for flame graphs.

## Image Optimization (Web + Mobile)

The single biggest leverage in most apps. Modern formats + sizing rules:

| Use case | Format | Notes |
|---|---|---|
| Photos (web) | AVIF (2026 default), WebP fallback | 30-50% smaller than JPEG |
| Photos (RN) | WebP | iOS 14+ & Android natively |
| Graphics / icons | SVG | Inline for critical above-fold |
| Animation | WebP / animated AVIF | Avoid GIF (huge) |
| Logos | SVG | Crisp at any density |
| Charts | SVG (small) / Canvas (large) | DOM cost vs raster |

**Sizing**:

- Serve at the size the device displays. Don't serve a 4000px JPG to a 400px container.
- Web: `<img srcset>` with multiple resolutions + `sizes` hint.
- RN: `react-native-fast-image` with explicit `style={{ width, height }}` + remote CDN that supports `?w=` resize.

**Loading**:

- `loading="lazy"` on below-fold images (web).
- `fetchpriority="high"` on the LCP image.
- Preconnect to the image CDN: `<link rel="preconnect" href="https://cdn.app.com">`.

**CDN**:

- Cloudflare Images, ImageKit, Imgix, Cloudinary — auto-format + auto-resize.
- Cache headers: `Cache-Control: public, max-age=31536000, immutable` for hashed asset URLs.

## Code Splitting

Web (Vite / Webpack / Next):

```typescript
// Lazy-load a route-scoped component
const Settings = lazy(() => import('./Settings'));

<Suspense fallback={<Spinner />}>
  <Settings />
</Suspense>
```

Rules:

- Split per route at minimum.
- Split large components (charts, rich-text editors, video players) on demand.
- Don't split things smaller than ~30KB — overhead outweighs.
- Preload the next likely route on hover / link visibility.

RN: 0.76+ bundle is one file by default; use Hermes lazy parse + tree-shake aggressively.

## Font Loading

Fonts are render-blocking. Best practices:

```css
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 400 700;             /* variable font, single file */
  font-display: swap;                /* show fallback immediately, swap when ready */
  src: url('/fonts/inter.woff2') format('woff2');
}
```

```html
<link rel="preload" href="/fonts/inter.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preconnect" href="https://fonts.app.com">
```

- Variable fonts (one file, all weights) over multiple static fonts.
- Subset fonts to characters you actually use (latin / latin-ext / etc.).
- `font-display: swap` — never block on font.
- Self-host critical fonts; don't depend on Google Fonts CDN for first paint.

## JavaScript Cost (Web)

The biggest INP / TTI killer. Defenses:

- **Bundle budget**: < 200KB compressed JS for the initial page.
- **Tree-shake aggressively**. `import { foo } from 'lib'` not `import * as lib`.
- **Avoid large UI libraries**: a custom dropdown is 100x smaller than `react-select`.
- **Defer non-critical scripts**: analytics, A/B testing, cookie banner load AFTER LCP.
- **Web workers** for heavy computation (PDF parse, CSV processing).
- **Streaming SSR** (React 19+) — TTFB drops, hydration starts earlier.

Lint rule: `no-default-export` for UI lib modules — easier tree-shake.

## Database Performance (cross-references db-design)

Most backend slowness is the database. Default fixes:

1. **Find the slow query** with `pg_stat_statements`:
   ```sql
   SELECT query, mean_exec_time, calls, total_exec_time
   FROM pg_stat_statements
   ORDER BY mean_exec_time DESC LIMIT 20;
   ```
2. **Run EXPLAIN (ANALYZE, BUFFERS)** on it.
3. **Add the missing index** (per `db-design`).
4. **N+1**: use eager loading or batch the lookup.
5. **Connection pool sized correctly** (per `db-design`).
6. **Add a cache layer** (Redis) for hot reads if DB is the bottleneck after indexing.

For Postgres-specific perf tools, see `db-design::postgres-patterns.md`.

## Caching Layers

| Layer | Tool | Use case |
|---|---|---|
| HTTP / CDN | Cloudflare, Fastly | Public, cacheable responses (homepage, static) |
| Reverse proxy | Nginx, Varnish | Same, on your edge |
| Application | Redis, Memcached | Hot reads, session data, rate-limit counters |
| Database query cache | (Postgres has no real query cache; use materialized views) | Aggregates that change infrequently |
| Service worker | Browser | Offline-first PWAs |
| Client-side | TanStack Query | Per-user request dedup + SWR |

Rules:

- **Cache invalidation is hard**. Pick TTL conservatively; explicit invalidate on writes.
- **Cache headers** must be set deliberately on EVERY endpoint (`no-store` for sensitive).
- **Edge cache** for anything that can be public.
- **Don't cache PII** at the edge (CDN).

## Profiling Workflow

### Backend (Go example)

```go
import _ "net/http/pprof"
go func() { _ = http.ListenAndServe("localhost:6060", nil) }()

// Then:
// go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30   (CPU)
// go tool pprof http://localhost:6060/debug/pprof/heap                  (heap)
// go tool pprof http://localhost:6060/debug/pprof/goroutine             (goroutine count)
```

### Web Frontend

- Chrome DevTools → Performance tab → record while reproducing.
- Look for: long tasks (> 50ms), layout shifts, render-blocking resources.
- Lighthouse → Performance audit → "Diagnostics" + "Opportunities".

### React Native

- Flipper → React DevTools profiler (component re-renders).
- Hermes Sampling Profiler (`hermes -enable-eval -sample-profiler`).
- Xcode Instruments (iOS) → Time Profiler / Allocations.
- Android Studio Profiler → CPU / Memory / Network.

## Performance Regressions in CI

Catch them before users do:

- **Bundle size budget** in webpack/vite config; fails build if bundle grows > 5%.
- **Lighthouse CI** (`@lhci/cli`) per PR on key pages; fails build on Performance score drop.
- **k6 load tests** weekly against staging; alert on P95 regression.
- **Detox / Maestro perf check** on mobile — startup time + first frame.

```yaml
# .github/workflows/perf.yml
- run: npm run build
- run: npx bundlesize    # fails if any chunk over budget
- run: npx @lhci/cli autorun --collect.url=https://staging.app.com/
```

## Common Performance Mistakes

1. **Optimizing without measuring** — guesswork; usually wrong.
2. **Hand-rolled caching** when TanStack Query / SWR exists.
3. **Re-renders ignored** — log re-render counts in dev; profile with React DevTools.
4. **N+1 queries unnoticed** until prod — add `pg_stat_statements` early.
5. **Big JPGs served everywhere** — modern formats + responsive `srcset`.
6. **Synchronous render-blocking script** in `<head>` — defer/async or load late.
7. **No `font-display: swap`** — invisible text until font loads.
8. **CSS `@import`** — serial loading. Use `<link>` for parallel.
9. **No connection pooling** to the DB — every request a new TCP handshake.
10. **Memory leaks**: unsubscribed listeners, retained closures, big arrays in module scope.
11. **Mobile: inline functions in render** of long lists — use `useCallback` + memoize rows.
12. **Mobile: AsyncStorage on app start** for big data — use MMKV (synchronous, 30x faster).
13. **Mobile: too many native module calls in render** — batch or move to lifecycle hooks.
14. **Backend: blocking I/O in async runtime** — measure with the runtime's debug mode.
15. **Backend: serialization-heavy responses** — Pydantic v2 is fast; v1 was a bottleneck.

## Pre-Launch Performance Checklist

See [assets/perf-checklist.md](assets/perf-checklist.md). Each item: a concrete metric or technique.

## Source Material

- *web.dev — Core Web Vitals*: <https://web.dev/articles/vitals>
- *Web Performance — Brendan Gregg* (book + blog): <https://www.brendangregg.com/>
- *Callstack — Ultimate Guide to React Native Optimization* (definitive RN perf reference).
- *Addy Osmani — Image Optimization*: <https://images.guide/>
- *Lighthouse Performance Scoring*: <https://developer.chrome.com/docs/lighthouse/performance/performance-scoring>
- *PostgreSQL — Performance Tips*: <https://www.postgresql.org/docs/current/performance-tips.html>
- *Go performance — uber-go/guide* and *cmd/pprof docs*.
