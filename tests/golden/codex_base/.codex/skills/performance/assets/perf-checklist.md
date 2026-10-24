# Performance Pre-Launch Checklist

Run before each release. Each item is a concrete metric or technique. Uncheck = fix or document waiver.

## Web Vitals (web client)

- [ ] **LCP** at P75 ≤ 2.5s on a real 4G mid-tier device.
- [ ] **INP** at P75 ≤ 200ms.
- [ ] **CLS** at P75 ≤ 0.1.
- [ ] **TTFB** at P75 ≤ 800ms.
- [ ] Lighthouse Performance score ≥ 90 on critical pages.
- [ ] `web-vitals` JS lib reporting to RUM (real-user monitoring).

## Image Optimization

- [ ] Modern format (AVIF/WebP) for raster images.
- [ ] Responsive `srcset` + `sizes` (web) OR CDN resize parameters (mobile).
- [ ] Every `<img>` has explicit `width` + `height` (or `aspect-ratio`).
- [ ] LCP image: `fetchpriority="high"` + `<link rel="preload">`.
- [ ] Below-fold images: `loading="lazy"`.
- [ ] CDN configured with `Cache-Control: public, max-age=31536000, immutable` for hashed URLs.

## Fonts

- [ ] Variable font (single file) over multi-weight static fonts.
- [ ] `font-display: swap`.
- [ ] Critical fonts preloaded (`<link rel="preload" as="font" crossorigin>`).
- [ ] Font subset to actual character set (no full Unicode for Latin-only sites).
- [ ] No render-blocking external font CSS (Google Fonts) for above-fold.

## JavaScript

- [ ] Initial JS bundle ≤ 200KB compressed.
- [ ] Code-split per route (web).
- [ ] Tree-shaking verified (named imports, ESM, no barrel re-exports).
- [ ] Heavy dependencies replaced (Moment → date-fns, full Lodash → individual functions).
- [ ] No render-blocking analytics / tag-manager script in `<head>`.
- [ ] Long tasks (> 50ms) profiled; broken up if found in critical path.

## Mobile (React Native)

- [ ] Hermes enabled both platforms.
- [ ] R8 / ProGuard enabled in Android release.
- [ ] App cold-start time ≤ 1.5s on Pixel 6a / iPhone 12 mini.
- [ ] App warm-start ≤ 500ms.
- [ ] Scroll FPS ≥ 60 on long lists (FlashList used).
- [ ] Animation FPS ≥ 60 (Reanimated worklets).
- [ ] Memory after 5 minutes' use ≤ 250MB.
- [ ] Bundle size: JS uncompressed ≤ 4MB.
- [ ] Native size per platform ≤ 50MB download.
- [ ] FastImage used for any image-heavy list.
- [ ] No `console.*` in release bundle (`babel-plugin-transform-remove-console`).
- [ ] Splash screen kept until first useful frame (`react-native-bootsplash`).
- [ ] Non-critical init deferred via `InteractionManager.runAfterInteractions`.

## Backend

- [ ] P50 latency ≤ 100ms; P95 ≤ 300ms; P99 ≤ 1s.
- [ ] Error rate ≤ 0.1% under normal load.
- [ ] CPU < 70% sustained, memory < 70% sustained at peak.
- [ ] DB connection pool < 60% utilization at peak.
- [ ] No N+1 queries in hot paths (verified with `pg_stat_statements`).
- [ ] All hot queries have appropriate indexes (verified with EXPLAIN ANALYZE).
- [ ] Cache hit rate > 90% for cached endpoints.
- [ ] APM / tracing wired up (OpenTelemetry → Datadog / Honeycomb / Tempo).

## Database (cross-references db-design)

- [ ] `pg_stat_statements` enabled and reviewed weekly.
- [ ] `auto_explain` on with 500ms threshold; logs reviewed.
- [ ] Connection pooling correct (per `db-design`).
- [ ] No long-running idle transactions (`idle_in_transaction_session_timeout` set).
- [ ] Backups verified by quarterly restore test.

## Caching

- [ ] CDN in front of static assets + cacheable endpoints.
- [ ] Cache headers explicit on every endpoint (`no-store` for sensitive).
- [ ] Application cache (Redis) for hot reads.
- [ ] Cache invalidation strategy documented per cached resource.
- [ ] No PII cached at edge (CDN).

## Network

- [ ] HTTP/2 or HTTP/3 enabled.
- [ ] Gzip / Brotli compression for responses > 1KB.
- [ ] `Connection: keep-alive` enabled.
- [ ] Preconnect to critical third-party origins.
- [ ] `<link rel="dns-prefetch">` for less-critical third-party origins.

## CI Regression Gates

- [ ] **Bundle-size budget** in CI; fails if any chunk > 5% larger.
- [ ] **Lighthouse CI** per PR on key pages; fails on Performance score drop.
- [ ] **k6 load test** weekly against staging; alerts on P95 regression.
- [ ] **Mobile**: cold-start time tracked per release.
- [ ] **APM**: p95 latency dashboards reviewed weekly; alerts on drift.

## Observability

- [ ] OpenTelemetry traces propagated end-to-end (RN client → backend → DB).
- [ ] RUM collects Web Vitals + custom metrics.
- [ ] Per-endpoint metrics: count, P50/P95/P99 latency, error rate.
- [ ] Slow-query log threshold set (~500ms).
- [ ] Per-screen mobile perf reported (cold-start, render time, error rate).

## Common Anti-Patterns Audit

- [ ] No optimization without measurement attached.
- [ ] No hand-rolled caching when TanStack Query / SWR exists.
- [ ] No re-renders ignored (React DevTools profiler reviewed for hot screens).
- [ ] No N+1 queries unnoticed.
- [ ] No giant JPEG hero images.
- [ ] No synchronous render-blocking script in `<head>`.
- [ ] No `font-display: block`.
- [ ] No `@import` in CSS.
- [ ] No connection-per-request to DB.

## Pre-Launch Smoke

- [ ] Cold-start measured on real mid-tier device (Pixel 6a / iPhone 12 mini).
- [ ] Critical user flow timed end-to-end.
- [ ] Network throttled to 4G slow → app still usable.
- [ ] CPU throttled 4× → no jank.

---

If any box is unchecked, document the reason in a tracking issue with an ETA.

## Per-Surface Quick Reference

```
Web:
  LCP ≤ 2.5s   INP ≤ 200ms   CLS ≤ 0.1   TTFB ≤ 800ms

Mobile (RN):
  Cold start ≤ 1.5s   Scroll FPS = 60   Memory ≤ 250MB
  JS bundle ≤ 4MB     Native size ≤ 50MB

Backend:
  P50 ≤ 100ms   P95 ≤ 300ms   P99 ≤ 1s   Errors ≤ 0.1%
  CPU ≤ 70%     Memory ≤ 70%   Pool ≤ 60%
```
