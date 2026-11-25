---
name: nextjs-react
tier: stack
domain: [frontend]
description: Use when creating or modifying React components, pages, layouts, or hooks in the Next.js frontend. Triggers on any .tsx/.ts file change under src/frontend/. Covers Server Component defaults, hydration safety, three-state async UI, error display mapping, localStorage SSR guards, and component extraction rules.
globs: "src/frontend/**/*.{ts,tsx}"
depends_on:
  - clean-code
  - frontend-fundamentals
last_reviewed: "2026-05-11"

---

This skill enforces Next.js 16 App Router and React patterns. It `depends_on: [clean-code, frontend-fundamentals]` which are loaded transitively — `clean-code` gives universal code quality, `frontend-fundamentals` gives stack-agnostic UI patterns (three-state async, hydration, a11y, SEO). This skill adds ONLY Next.js-App-Router and React-version-specific layering on top.

## Pre-Code Checklist

Before writing or modifying any `.ts`/`.tsx` file:

- [ ] Read `docs/engineering/frontend-rules.md`
- [ ] If touching data fetching or rendering logic: read `docs/engineering/frontend-rendering-rules.md`
- [ ] If touching design, layout, or styling: read `STYLE_GUIDE.md` + the relevant file in `docs/design/`
- [ ] If touching API calls or error handling: read `docs/api-contracts/error-format.md`
- [ ] Search the repo for existing components and hooks before creating new ones (use Grep/Glob)

## 1. Server Components First

Default to **Server Components**. Never add `'use client'` unless the component genuinely requires it.

### When to use `'use client'`

- Browser APIs (`window`, `document`, `navigator`, `localStorage`)
- Event handlers (`onClick`, `onChange`, `onSubmit`)
- React state or effects (`useState`, `useEffect`, `useReducer`, `useRef` with mutations)
- Third-party client-only libraries (e.g., motion, chart libraries)

### Correct — Server Component (default)

```tsx
// app/products/[slug]/page.tsx
// No 'use client' — this is a Server Component
import { getProduct } from "@/lib/api/products";
import { ProductDetails } from "@/components/products/product-details";

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const product = await getProduct(slug);

  return <ProductDetails product={product} />;
}
```

### Correct — Client Component (only when needed)

```tsx
// components/products/add-to-cart-button.tsx
"use client";

import { useState } from "react";

interface AddToCartButtonProps {
  productId: string;
  onAdd: (id: string) => void;
}

export function AddToCartButton({ productId, onAdd }: AddToCartButtonProps) {
  const [isAdding, setIsAdding] = useState(false);

  async function handleClick() {
    setIsAdding(true);
    try {
      await onAdd(productId);
    } finally {
      setIsAdding(false);
    }
  }

  return (
    <button onClick={handleClick} disabled={isAdding}>
      {isAdding ? "Adding..." : "Add to Cart"}
    </button>
  );
}
```

### Wrong — Unnecessary client directive

```tsx
// BAD: 'use client' added for no reason — this is pure rendering
"use client";

export function ProductCard({ name, price }: { name: string; price: number }) {
  return (
    <div>
      <h3>{name}</h3>
      <p>${price}</p>
    </div>
  );
}
```

## 2. Hydration Safety

The server-rendered HTML must match the client's first render exactly. Mismatches cause hydration errors, layout flicker, and broken UI.

### Rule

`useState` initializers MUST return the **same value** on both server and client. For client-only values, initialize with `undefined` or `null` and set the real value in `useEffect`.

### Correct — Client-only value via useEffect

```tsx
"use client";

import { useState, useEffect } from "react";

export function ViewportLabel() {
  const [width, setWidth] = useState<number | undefined>(undefined);

  useEffect(() => {
    setWidth(window.innerWidth);

    function handleResize() {
      setWidth(window.innerWidth);
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (width === undefined) {
    return <span>Loading...</span>;
  }

  return <span>Viewport: {width}px</span>;
}
```

### Wrong — Divergent initializer

```tsx
// BAD: Server renders 0, client renders window.innerWidth → hydration mismatch
"use client";

import { useState } from "react";

export function ViewportLabel() {
  const [width] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth : 0,
  );

  return <span>Viewport: {width}px</span>;
}
```

### Wrong — Conditional rendering on typeof window

```tsx
// BAD: Server renders nothing, client renders content → hydration mismatch
"use client";

export function ClientOnlyBanner() {
  if (typeof window === "undefined") return null;

  return <div>Welcome, {window.navigator.userAgent}</div>;
}
```

### Intentional sync setState

When you intentionally call `setState` synchronously during render (e.g., to correct a mismatch), add an eslint-disable comment explaining why:

```tsx
// eslint-disable-next-line react-hooks/exhaustive-deps -- sync correction
// for server/client value alignment on first client render
```

## 3. Three-State Async UI

Every async operation that drives UI must handle **all three states**: loading, error, and empty/success. Never show stale data during a fetch. Never show a blank screen on error.

### Correct — All three states

```tsx
"use client";

import { useState, useEffect } from "react";
import type { Product } from "@/types/product";

export function ProductList({ categoryId }: { categoryId: string }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);

      try {
        const res = await fetch(`/api/products?category=${categoryId}`);
        if (!res.ok) throw new Error("Failed to load products");
        const data: Product[] = await res.json();

        if (!cancelled) {
          setProducts(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unexpected error");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, [categoryId]);

  // State 1: Loading
  if (isLoading) {
    return <ProductListSkeleton />;
  }

  // State 2: Error
  if (error) {
    return (
      <div role="alert">
        <p>Could not load products: {error}</p>
        <button onClick={() => setError(null)}>Retry</button>
      </div>
    );
  }

  // State 3: Empty
  if (products.length === 0) {
    return <p>No products found in this category.</p>;
  }

  // State 4: Success with data
  return (
    <ul>
      {products.map((p) => (
        <li key={p.id}>{p.name}</li>
      ))}
    </ul>
  );
}
```

### Wrong — Missing states

```tsx
// BAD: No loading state, no error state, no empty state
"use client";

import { useState, useEffect } from "react";

export function ProductList({ categoryId }: { categoryId: string }) {
  const [products, setProducts] = useState([]);

  useEffect(() => {
    fetch(`/api/products?category=${categoryId}`)
      .then((r) => r.json())
      .then(setProducts);
  }, [categoryId]);

  return (
    <ul>
      {products.map((p) => (
        <li key={p.id}>{p.name}</li>
      ))}
    </ul>
  );
}
```

## 4. Error Display

Never show raw server messages to users. Map API error codes to user-facing i18n keys.

### Pattern

```
API error_code → i18n key: errors.<domain>.<ERROR_CODE>
```

### Correct — Mapped error display

```tsx
import { useTranslation } from "@/lib/i18n";

const ERROR_KEY_MAP: Record<string, string> = {
  PRODUCT_NOT_FOUND: "errors.products.PRODUCT_NOT_FOUND",
  PRODUCT_UNAVAILABLE: "errors.products.PRODUCT_UNAVAILABLE",
  INSUFFICIENT_FUNDS: "errors.payments.INSUFFICIENT_FUNDS",
};

function getErrorMessage(errorCode: string | undefined, t: (key: string) => string): string {
  if (errorCode && ERROR_KEY_MAP[errorCode]) {
    return t(ERROR_KEY_MAP[errorCode]);
  }
  return t("errors.generic.UNEXPECTED");
}
```

### Error placement rules

| Error Type | Display Method |
|---|---|
| Transient (network, timeout) | Toast notification with retry |
| Form validation | Inline below the field |
| Permission / auth | Redirect or full-page message |
| Not found | Dedicated empty state or 404 page |

### Wrong — Raw server message

```tsx
// BAD: Shows raw server error to user
catch (err) {
  setError(err.message); // "IntegrityError: duplicate key violates..."
}
```

## 5. localStorage Pattern

Accessing `localStorage` requires an SSR guard because it does not exist on the server.

### Correct — Lazy initializer with SSR guard

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";

function useLocalStorage<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(fallback);
  const [isHydrated, setIsHydrated] = useState(false);

  // Read from localStorage after mount (client only)
  useEffect(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored !== null) {
        setValue(JSON.parse(stored) as T);
      }
    } catch {
      // localStorage unavailable or corrupted — keep fallback
    }
    setIsHydrated(true);
  }, [key]);

  // Write to localStorage on changes (after hydration)
  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // Storage full or unavailable — state still updates in memory
      }
    },
    [key],
  );

  return [value, set, isHydrated] as const;
}
```

### Rule: Always try/catch localStorage calls

Every `localStorage.getItem` and `localStorage.setItem` call MUST be wrapped in `try/catch`. Storage can throw when full (`QuotaExceededError`), disabled by privacy settings, or unavailable in SSR. Never call `localStorage.setItem(...)` without a surrounding try/catch — even outside the `useLocalStorage` hook.

### Wrong — Direct access in initializer

```tsx
// BAD: Crashes on server, hydration mismatch on client
"use client";

import { useState } from "react";

function useLocalStorage<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(() => {
    const stored = localStorage.getItem(key); // ReferenceError on server
    return stored ? JSON.parse(stored) : fallback;
  });

  return [value, setValue] as const;
}
```

## 6. Component Extraction

Never define a component inside another component. Inner components are recreated on every render, destroying state and DOM nodes.

### Correct — Extracted above parent

```tsx
// components/products/product-card.tsx
interface PriceBadgeProps {
  price: number;
  discount?: number;
}

function PriceBadge({ price, discount }: PriceBadgeProps) {
  if (discount) {
    return (
      <span>
        <s>${price}</s> ${price - discount}
      </span>
    );
  }
  return <span>${price}</span>;
}

interface ProductCardProps {
  name: string;
  price: number;
  discount?: number;
}

export function ProductCard({ name, price, discount }: ProductCardProps) {
  return (
    <div>
      <h3>{name}</h3>
      <PriceBadge price={price} discount={discount} />
    </div>
  );
}
```

### Wrong — Component defined inside parent

```tsx
// BAD: PriceBadge is recreated on every render of ProductCard
export function ProductCard({ name, price, discount }: ProductCardProps) {
  // This component is redefined every render — causes remount, lost state
  function PriceBadge() {
    if (discount) {
      return (
        <span>
          <s>${price}</s> ${price - discount}
        </span>
      );
    }
    return <span>${price}</span>;
  }

  return (
    <div>
      <h3>{name}</h3>
      <PriceBadge />
    </div>
  );
}
```

## 7. Import and File Conventions

- Use `@/` path aliases for all imports (never relative paths beyond `./`)
- One exported component per file; filename matches export name in kebab-case
- Co-locate test files: `component-name.test.tsx` next to `component-name.tsx`
- Barrel exports (`index.ts`) only at feature boundaries, not per-component

## Post-Code Checklist

After writing or modifying any frontend code, verify all points before committing:

- [ ] **Server-first:** No unnecessary `'use client'` directives
- [ ] **Hydration-safe:** `useState` initializers return identical values on server and client
- [ ] **Three-state UI:** Every async operation shows loading, error, and empty states
- [ ] **Error mapping:** API errors mapped to i18n keys — no raw server messages shown
- [ ] **localStorage guarded:** All `localStorage` access wrapped in SSR-safe pattern
- [ ] **Components extracted:** No components defined inside other components
- [ ] **Responsive verified:** Visual smoke test at 375px, 768px, and 1280px
- [ ] **Lint passes:** `cd frontend && npm run lint` exits cleanly
- [ ] **Build passes:** `cd frontend && npm run build` exits cleanly
