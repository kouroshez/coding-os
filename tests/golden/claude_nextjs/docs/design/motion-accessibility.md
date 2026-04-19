<!-- domain:ALL | layer:reference | ssot:true | updated:2026-03-13 -->

# Motion & Accessibility

Purpose: Animation guidelines, reduced-motion support, and WCAG compliance.
Read when: Task involves animations, transitions, or accessibility compliance.
Skip when: Static layouts or non-interactive features.
Read next: Components (components-patterns.md) or the frontend-ui playbook.

> Nav: [Docs Index](../00-index.md) | [Style Guide](../../STYLE_GUIDE.md)

---

## 1. Motion & Animation

### 1.1 Motion Philosophy

- Animation should **signal state changes**, **guide attention**, and **create delight**
- Never distract or delay the user
- The absence of _expected_ motion feels broken
- One well-crafted hero animation > twenty scattered micro-interactions

### 1.2 Timing Scale

| Name        | Duration | Tailwind       | Use Case                     |
| :---------- | :------- | :------------- | :--------------------------- |
| **Instant** | 50ms     | `duration-50`  | Micro-feedback (hover color) |
| **Fast**    | 150ms    | `duration-150` | UI feedback (button click)   |
| **Normal**  | 300ms    | `duration-300` | Standard transitions         |
| **Slow**    | 500ms    | `duration-500` | Complex animations           |
| **Hero**    | 700ms+   | `duration-700` | Hero section animations      |

### 1.3 Easing Functions

| Name          | CSS Value                      | Use Case              |
| :------------ | :----------------------------- | :-------------------- |
| `ease-out`    | `cubic-bezier(0, 0, 0.2, 1)`   | Elements entering     |
| `ease-in`     | `cubic-bezier(0.4, 0, 1, 1)`   | Elements exiting      |
| `ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | On-screen movement    |
| `spring`      | Framer Motion                  | Playful, organic feel |

### 1.4 Implementation (Framer Motion)

```tsx
// Entrance animation
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.5, ease: "easeOut" }}
>
```

---

## 2. Performance Targets

> [!IMPORTANT]
> Speed and stability are **user experience concerns**, not just technical concerns.

| Metric                             | Target     | Tool                    |
| :--------------------------------- | :--------- | :---------------------- |
| **LCP** (Largest Contentful Paint) | < 2.5s     | Lighthouse              |
| **FCP** (First Contentful Paint)   | < 1.5s     | Lighthouse              |
| **CLS** (Cumulative Layout Shift)  | < 0.1      | Lighthouse              |
| **Animation Frame Rate**           | 60fps      | DevTools                |
| **Bundle Size (First Load)**       | < 200KB JS | `@next/bundle-analyzer` |

### Performance-Impacting Decisions

- Lazy load images below the fold (`loading="lazy"`)
- Use `next/image` with explicit `sizes`
- Preload critical fonts
- Code-split large components with `next/dynamic`
- Don't load heavy animations on mobile

---

## 3. Accessibility Requirements

> [!CAUTION]
> Accessibility is not a feature -- it's the **foundation**.

### Non-Negotiable Requirements

| Element                 | Requirement                                                    |
| :---------------------- | :------------------------------------------------------------- |
| **Color Contrast**      | WCAG AA (4.5:1 for text, 3:1 for large text)                   |
| **Focus States**        | Visible, high-contrast focus rings on ALL interactive elements |
| **Touch Targets**       | Minimum 44x44px                                                |
| **Keyboard Navigation** | All interactive elements reachable via Tab                     |
| **Semantic HTML**       | Proper `<h1>`-`<h6>` hierarchy, landmarks (`<main>`, `<nav>`)  |
| **Alt Text**            | Meaningful descriptions for all images                         |
| **ARIA Labels**         | For icons and non-text elements                                |

### Focus Ring Standard

```css
/* Default focus ring */
.focus-visible:focus {
  outline: 2px solid rgb(var(--brand-1));
  outline-offset: 2px;
}
```

---

## 4. Responsive Design Patterns

> [!IMPORTANT]
> Use standard Tailwind breakpoints. Ensure server-side rendering matches client structure to avoid hydration errors.

### 4.1 Breakpoints

- **Mobile First**: Default styles are mobile.
- **Tablet**: `md:` (768px+)
- **Desktop**: `lg:` (1024px+)
- **Wide**: `xl:` (1280px+)

### 4.2 Common Patterns

```tsx
// Stack on mobile, Row on desktop
<div className="flex flex-col md:flex-row gap-4">

// Hide on mobile, Show on desktop
<div className="hidden md:block">

// Container Padding (Safe Area)
// Must be px-6 on mobile for breathing room
<div className="px-6 sm:px-8 lg:px-12">
```

### 4.3 Layout Safeguards

1. **Global Scroll Lock**: `html, body { overflow-x: hidden; }` must be applied to prevent horizontal scroll on narrow devices.
2. **Text Constraint**: Use `break-words` on large headings.
3. **Narrow Screen Logic**: Hide non-essential text/icons on screens < 340px (Galaxy Fold).
