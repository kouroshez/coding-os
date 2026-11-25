# Web Vitals — Per-Metric Optimization

The four metrics Google uses for ranking + user-experience scoring. Each has distinct optimizations; conflating them wastes effort.

## LCP — Largest Contentful Paint

When the largest above-fold element renders. Almost always a hero image or large headline.

**Target**: ≤ 2.5s at the 75th percentile of users.

### Find the LCP Element

Chrome DevTools → Performance tab → "Web Vitals" lane → click the LCP marker → see the highlighted element.

Or in code:

```javascript
import { onLCP } from 'web-vitals';
onLCP((metric) => {
  console.log('LCP element:', metric.entries[0]?.element);
  console.log('LCP value:', metric.value);
});
```

### Optimization Tactics (in order of impact)

1. **Preload the LCP image**:
   ```html
   <link rel="preload" as="image" href="/hero.avif" fetchpriority="high">
   ```
2. **Set `fetchpriority="high"`** on the LCP `<img>`:
   ```html
   <img src="/hero.avif" fetchpriority="high" alt="Hero" />
   ```
3. **Don't lazy-load the LCP image** — it's above the fold; serve immediately.
4. **Compress + modern format** — AVIF / WebP, `srcset` for resolution.
5. **Self-host critical fonts** + preload — text-LCP blocked on font.
6. **Reduce render-blocking JS** — every blocking script delays the first paint.
7. **Server response time (TTFB) < 800ms** — LCP is bounded by TTFB + render time.
8. **Use a CDN** for static assets — cuts download time.
9. **Inline critical CSS** for the above-fold; defer the rest.

### Common LCP Killers

- 4MB hero image, no compression.
- Blocking third-party script (cookie banner, A/B test) loaded synchronously in `<head>`.
- Server response > 1s due to slow query.
- `font-display: block` or no `font-display` (default = block).
- LCP image inside a JS-rendered component (delays until React hydrates).

## INP — Interaction to Next Paint

Replaced FID in March 2024. Measures the worst input latency in the session — click, tap, key press.

**Target**: ≤ 200ms.

### How It's Measured

Browser tracks every interaction's latency from input event to next paint. INP = the worst (or 98th percentile for sessions with many interactions).

### Optimization Tactics

1. **Break up long tasks** (> 50ms) — scheduler.yield() or `setTimeout(...)`:
   ```javascript
   async function processBigList(items) {
     for (const item of items) {
       processItem(item);
       if (typeof scheduler !== 'undefined' && scheduler.yield) {
         await scheduler.yield();   // yield to browser between items
       }
     }
   }
   ```
2. **Use `useDeferredValue` / `useTransition`** in React 18+ for low-priority updates that shouldn't block input.
3. **Move heavy computation off the main thread** — Web Workers.
4. **Avoid synchronous event handlers** that do too much. Defer non-critical work.
5. **Audit third-party scripts** — they often hog the main thread (analytics, A/B test).
6. **Avoid layout-thrashing reads/writes** in event handlers.
7. **Reduce React re-render cost** — memoize, virtualize lists.

### Profile with Chrome DevTools

Performance tab → record while clicking the slow interaction → look for:

- "Long Task" annotations in the Main thread track.
- Interaction → "Pointer down" → "Click" markers — see the gap to "Paint".

### Common INP Killers

- Synchronous JSON parse / large array operations in click handler.
- Re-render of a giant tree on every input change.
- Blocking analytics on click.
- Third-party scripts that yield the thread badly.

## CLS — Cumulative Layout Shift

Visual stability — how much elements move around as the page loads / interactions happen.

**Target**: ≤ 0.1.

### What Causes Shifts

- Image without explicit dimensions → reflow when image loads.
- Web font swap → reflow when font loads (`font-display: swap` is good but causes a small shift; that's OK).
- Ads / embeds inserted dynamically without reserved space.
- Cookie banner appearing and pushing content down.

### Fix Tactics

1. **`width` + `height` (or `aspect-ratio`)** on every image:
   ```html
   <img src="/hero.avif" width="1200" height="600" />
   <!-- Browser reserves space; no shift on load. -->
   ```
   ```css
   img { aspect-ratio: 2/1; }
   ```
2. **`min-height`** on containers that load async content (lists, embeds).
3. **`size-adjust`, `ascent-override`** on `@font-face` to match fallback font metrics — minimizes swap shift.
4. **Insert dynamic UI without pushing content** — overlay (modal / toast) instead of inline.
5. **Skeleton loaders** that match the final content's dimensions.
6. **Reserve space for ads** — fixed-size containers; no "shrink to fit" after ad loads.

### Profile

Lighthouse → "Avoid large layout shifts" → lists every shift with the element + visualizing the movement.

### Common CLS Killers

- Hero `<img>` without width/height.
- Cookie banner appearing 2 seconds in, pushing content.
- Auto-loading more items at the top of an infinite list.
- Embedded YouTube / map iframe loaded without dimensions.

## TTFB — Time to First Byte

Server response time. Bound for LCP.

**Target**: ≤ 800ms.

### Optimization

- **Cache hot endpoints** at the CDN.
- **Optimize the slow query** (per `db-design`).
- **Async I/O** done concurrently, not serially.
- **Edge functions** for region-relevant content (Cloudflare Workers, Vercel Edge).
- **Connection: keep-alive** + HTTP/2 / HTTP/3 — reduces handshake cost.
- **Faster runtime** (V8/Hermes/Bun for JS, Pypy/Cython for hot Python paths).

## INP-Specific React Patterns

### useTransition for "stale OK" updates

```typescript
import { useTransition, useState } from 'react';

const [isPending, startTransition] = useTransition();
const [filter, setFilter] = useState('');

const onChange = (e) => {
  // High priority: update the input value.
  setFilter(e.target.value);
  // Low priority: filter the list — can be deferred.
  startTransition(() => {
    setFilteredList(computeFilteredList(e.target.value));
  });
};
```

### useDeferredValue for derived expensive UI

```typescript
const deferredQuery = useDeferredValue(query);
const results = useMemo(() => searchHeavy(deferredQuery), [deferredQuery]);
```

### Memo + Virtual Lists

For lists > 100 items, virtualize (`@tanstack/react-virtual`). Recycles DOM nodes; renders only visible.

```typescript
import { useVirtualizer } from '@tanstack/react-virtual';
const rowVirtualizer = useVirtualizer({
  count: items.length,
  estimateSize: () => 48,
  getScrollElement: () => parentRef.current,
});
// Render only rowVirtualizer.getVirtualItems().
```

## Tools

| Tool | Use |
|---|---|
| **Lighthouse** (Chrome DevTools or `@lhci/cli`) | Per-page audit, CI integration |
| **PageSpeed Insights** | Real-user CrUX data + lab Lighthouse |
| **WebPageTest** | More detail than Lighthouse, real device options |
| **Chrome DevTools Performance** | Frame-by-frame trace |
| **`web-vitals` JS lib** | Real-user monitoring beacon |
| **DebugBear / SpeedCurve** | Continuous monitoring + alerting |

## Source Material

- *web.dev — Core Web Vitals*: <https://web.dev/articles/vitals>
- *web.dev — INP* (deep dive): <https://web.dev/articles/inp>
- *web.dev — Optimize LCP*: <https://web.dev/articles/optimize-lcp>
- *web.dev — Optimize CLS*: <https://web.dev/articles/optimize-cls>
- *Smashing Magazine — Front-End Performance Checklist 2025*.
- *Addy Osmani — Optimize INP* talks.
