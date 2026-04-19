<!-- domain:ALL | layer:reference | ssot:true | updated:2026-03-13 -->

# Typography & Spacing

Purpose: Font stacks, type scale, and spacing/grid rules.
Read when: Task involves typography, spacing, layout, or responsive grid.
Skip when: Color or component styling without layout changes.
Read next: Colors and tokens (colors-tokens.md) or components (components-patterns.md).

> Nav: [Docs Index](../00-index.md) | [Style Guide](../../STYLE_GUIDE.md)

---

## 1. Font Families

- **Headings**: `Baloo 2` (Rounded, Friendly, Modern) — Weights: 700 (Bold)
- **Body**: `Inter` (Clean, Legible, Standard) — Weights: 400 (Regular), 500 (Medium), 600 (SemiBold)

## 2. Type Scale (Tailwind)

| Class       | Size (rem) | Size (px) | Line Height | Usage                    |
| :---------- | :--------- | :-------- | :---------- | :----------------------- |
| `text-xs`   | 0.75       | 12px      | 1rem        | Badges, Microcopy        |
| `text-sm`   | 0.875      | 14px      | 1.25rem     | UI Labels, Metadata      |
| `text-base` | 1          | 16px      | 1.5rem      | **Default Body Text**    |
| `text-lg`   | 1.125      | 18px      | 1.75rem     | Intro paragraphs         |
| `text-xl`   | 1.25       | 20px      | 1.75rem     | Section Headers (H3)     |
| `text-2xl`  | 1.5        | 24px      | 2rem        | Card Titles (H2)         |
| `text-3xl`  | 1.875      | 30px      | 2.25rem     | Page Titles (H1 Mobile)  |
| `text-4xl`  | 2.25       | 36px      | 2.5rem      | Page Titles (H1 Desktop) |
| `text-5xl`  | 3          | 48px      | 1           | Hero Headings            |

---

## 3. Spacing & Layout

We follow a **4pt grid system** (Tailwind default).

### 3.1 Container Configuration

```javascript
// tailwind.config.ts
container: {
  center: true,
  padding: {
    DEFAULT: '1rem',    // 16px mobile
    sm: '1.5rem',       // 24px small
    lg: '2rem',         // 32px large
    xl: '2rem',
    '2xl': '2rem',
  },
  screens: {
    '2xl': '1400px',    // Max container width (Audit Fix)
  },
}
```

### 3.2 Section Spacing (`py-`)

- **Tight**: `py-8` (32px)
- **Normal**: `py-16` (64px) — **Standard Section**
- **Loose**: `py-24` (96px) — **Hero / Feature Splits**

### 3.3 Gap

- **Stack (Vertical)**: `space-y-4` (Forms), `space-y-6` (Content)
- **Grid (Horizontal)**: `gap-6` (Cards), `gap-8` (Columns)

---

## 4. Z-Index Layering System

> [!IMPORTANT]
> All z-index values MUST follow this scale. Do not use arbitrary values.

| Layer       | Z-Index | Tailwind Class | Elements                           |
| :---------- | :------ | :------------- | :--------------------------------- |
| **Base**    | 0       | `z-0`          | Page content, sections             |
| **Raised**  | 10      | `z-raised`     | Cards with hover, dropdowns        |
| **Sticky**  | 40      | `z-sticky`     | Sticky bottom bar, floating CTAs   |
| **Header**  | 50      | `z-header`     | Site header (always above content) |
| **Overlay** | 60      | `z-overlay`    | Backdrop for modals                |
| **Modal**   | 70      | `z-modal`      | Modal dialogs                      |
| **Toast**   | 80      | `z-toast`      | Toast notifications                |
| **Tooltip** | 90      | `z-tooltip`    | Tooltips, popovers                 |
| **Max**     | 100     | `z-max`        | **Mobile Nav**, Emergency overlays |

### Z-Index Rules

1. **Header (`z-header`)** must ALWAYS be above content sections.
2. **Sticky bars** use `z-sticky` (below header).
3. **Mobile Nav / Modals** MUST use `z-max` (100) to overlay sticky headers.
4. **Use Semantic Tokens**: `z-modal` instead of `z-[70]`.
5. **Stacking context**: Use `isolate` class on parent containers if needed.

---

## 5. Grid System

We use a **12-column grid** for main layouts.

```tsx
<div className="grid grid-cols-4 md:grid-cols-8 lg:grid-cols-12 gap-6">
  <div className="col-span-4">Sidebar</div>
  <div className="col-span-8">Content</div>
</div>
```
