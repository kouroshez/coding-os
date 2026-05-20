<!-- domain:ALL | layer:reference | ssot:true | updated:2026-03-13 -->

# Components & Patterns

Purpose: Reusable UI component patterns, states, and composition rules.
Read when: Task involves building or styling UI components.
Skip when: Layout or color adjustments alone.
Read next: Colors (colors-tokens.md), typography (typography-spacing.md), or motion (motion-accessibility.md).

> Nav: [Docs Index](../00-index.md) | [Style Guide](../../STYLE_GUIDE.md)

---

## 1. Design Philosophy

### Visual Excellence Standard

ExampleApp's design must feel **premium, modern, and conversion-focused**.

> [!TIP]
> Think like an experienced graphic designer with knowledge of:
>
> - Sales psychology & CRO (Conversion Rate Optimization)
> - 3D elements & abstract shapes for visual interest
> - Micro-animations for engagement
> - Premium color palettes (no generic red/blue/green)

### Design Principles

1. **Wow Factor**: First impression must impress - use gradients, subtle animations, glassmorphism
2. **Trust Building**: Social proof, security badges, professional typography
3. **Clear Hierarchy**: Guide the eye to CTAs with size, color, and whitespace
4. **Mobile Excellence**: 60%+ traffic is mobile - design mobile-first
5. **Fast Perceived Performance**: Skeleton loaders, optimistic UI, smooth transitions

### What to Avoid

- Generic/flat designs
- Default browser fonts
- Plain solid color backgrounds
- Static, lifeless interfaces
- Placeholder images (use generated or real assets)

### What to Embrace

- Curated color harmonies (HSL-based, not plain hex)
- Subtle gradients and shadows
- Micro-interactions (hover effects, smooth transitions)
- Modern typography (Baloo 2 + Inter)
- Glassmorphism for overlays (when appropriate)
- Abstract decorative elements (subtle, not distracting)

---

## 2. Site Branding

- **Site Name**: `ExampleApp` (not "Example" or "example")
- **Logo Text**: "ExampleApp" or "Example App" (with space for readability)
- **Domain**: example.com

---

## 3. Buttons

The most critical conversion element.

### Primary (Money Button)

- **Background**: `bg-gradient-to-r from-brand-1 to-brand-3`
- **Text**: White, Bold (Inter Medium/Semibold)
- **Visuals**: Mild shadow `shadow-lg`, rounded `rounded-full` or `rounded-xl`
- **Hover**: Brightness up / Scale 1.05

### Secondary (Outline)

- **Border**: `border border-border`
- **Background**: Transparent (hover: surface-2)
- **Text**: `text-text-secondary` (hover: text-text)

### Ghost (Link)

- **Background**: None
- **Text**: `text-text-muted` (hover: text-brand-1)

---

## 4. Cards (Surface)

- **Base**: `bg-surface` border `border-border`
- **Shadow**: `shadow-sm` (default) -> `shadow-md` (hover)
- **Radius**: `rounded-2xl` (Standard for Containers/Cards)
- **Padding**: `p-6` (default)
- **Inputs/Buttons**: `rounded-xl` (Standard for Interactive Elements)
- **Borders**: Thin, crisp borders (`1px`) in light mode

---

## 5. Loading States

**Skeleton Loaders** are preferred over spinners for initial load.

- **Animation**: `animate-pulse`
- **Color**: `bg-muted` (or `bg-surface-2`)
- **Radius**: Match the content being loaded (e.g. `rounded-full` for avatars)

```tsx
<div className="space-y-2">
  <div className="h-4 w-[250px] animate-pulse rounded bg-muted" />
  <div className="h-4 w-[200px] animate-pulse rounded bg-muted" />
</div>
```

---

## 6. Empty States

Always provide a path forward.

- **Visual**: Icon or Illustration
- **Text**: Clear "Status" + "Solution"
- **Action**: Button to resolve/create

---

## 7. Design Tradeoffs

> Every philosophy accepts certain tradeoffs. Being explicit prevents surprise.

| We Choose           | Over          | Because                          |
| :------------------ | :------------ | :------------------------------- |
| **Opinionated**     | Neutral       | Memorable > forgettable          |
| **Consistent**      | Flexible      | Maintainable > one-off solutions |
| **Bold**            | Safe          | Standing out > blending in       |
| **Semantic Tokens** | Direct Values | Scalability > initial speed      |
| **Fewer Options**   | More Options  | Clarity > choice paralysis       |
| **Performance**     | Features      | Fast basics > slow extras        |
| **Mobile-First**    | Desktop-First | 60%+ traffic is mobile           |

---

## 8. Anti-Patterns

| Anti-Pattern               | Why Harmful                   | Alternative                         |
| :------------------------- | :---------------------------- | :---------------------------------- |
| **Hardcoded colors**       | Impossible to theme           | Use semantic tokens                 |
| **Inconsistent spacing**   | Creates visual noise          | Use 4pt spacing scale               |
| **Too many fonts**         | Looks chaotic                 | Max 2 fonts                         |
| **Purple AI gradients**    | Overused, generic             | Distinctive palette                 |
| **Motion without purpose** | Distracting, unprofessional   | Animate with intent                 |
| **Ignoring dark mode**     | Excludes users                | Design both modes                   |
| **className overrides**    | Unmaintainable                | Create component variants           |
| **Missing focus states**   | Accessibility failure         | Always show focus rings             |
| **Placeholder images**     | Unprofessional                | Generate or use real assets         |
| **Generic stock photos**   | Feels corporate/fake          | Custom or AI-generated              |
| **CSS Media Query Hacks**  | Breaks composition            | Use standard Tailwind               |
| **Double Mobile Headers**  | Confusing UI, double triggers | Single global header                |
| **Low Z-Index Modals**     | Hides under sticky headers    | Use `z-max` (100)                   |
| **Horizontal Overflow**    | White bars on mobile edges    | `overflow-x-hidden` + `break-words` |
| **Tight Mobile Padding**   | Cramped, cheap feel           | Min `px-6` (24px) padding           |
