<!-- domain:ALL | layer:reference | ssot:true | updated:2026-03-13 -->

# Colors & Tokens

Purpose: Design token values — colors, semantic aliases, and dark-mode mappings.
Read when: Task involves color selection, theme configuration, or design tokens.
Skip when: Code-only change with no visual impact.
Read next: Typography and spacing (typography-spacing.md) or components (components-patterns.md).

> Nav: [Docs Index](../00-index.md) | [Style Guide](../../STYLE_GUIDE.md)

---

## 1. Theme Configuration

### Default Mode

- **Light mode is the DEFAULT**. Users see light mode on first visit.
- Dark mode is only activated when user explicitly toggles.

### Implementation

```javascript
// tailwind.config.ts
darkMode: 'class', // NOT 'media'
```

- Store preference in `localStorage` with key `theme`
- Respect `prefers-color-scheme` only on first visit if no stored preference
- Apply `.dark` class to `<html>` element

### Theme Toggle Component

- **Location**: Header (desktop: right side near user menu, mobile: in hamburger menu)
- **Icons**: Sun (light) / Moon (dark)
- **Transition**: `transition-colors duration-200`
- **Accessibility**: `aria-label="Toggle theme"`

---

## 2. Color Palette (CSS Variables)

> [!CAUTION]
> **All colors MUST be defined as raw RGB values** (e.g., `67 118 248`) not Hex.
> This enables Tailwind's opacity modifier: `bg-brand-1/50` -> `rgba(67, 118, 248, 0.5)`

> [!WARNING]
> **Shadcn vs ExampleApp Colors**: Shadcn uses `--background` (white). ExampleApp uses `--bg` (#F6F7F7).
> **Resolution**: Override Shadcn's `--background` to match `--bg` in globals.css.

### 2.1 Brand Colors (Vibrant Gradient)

| Token           | Light RGB     | Dark RGB     | Hex Reference     | Usage                 |
| :-------------- | :------------ | :----------- | :---------------- | :-------------------- |
| `--brand-1`     | `68 119 248`  | `68 119 248` | #4477F8           | Primary Blue          |
| `--brand-2`     | `112 68 248`  | `112 68 248` | #7044F8           | Middle Purple         |
| `--brand-3`     | `184 68 248`  | `184 68 248` | #B844F8           | End Pink/Purple       |
| `--accent-soft` | `208 221 255` | `30 41 59`   | #D0DDFF / #1E293B | Background highlights |

### 2.2 Surface & Backgrounds (Canvas)

| Token         | Light RGB     | Dark RGB   | Description                      |
| :------------ | :------------ | :--------- | :------------------------------- |
| `--bg`        | `246 247 247` | `11 16 32` | Main window background           |
| `--bg-canvas` | `228 230 229` | `7 11 22`  | App background outside container |
| `--surface`   | `255 255 255` | `15 22 48` | Cards, Modals, Dropdowns         |
| `--surface-2` | `248 248 248` | `18 27 58` | Nested sections, inputs          |

### 2.3 Typography Colors

| Token              | Light RGB     | Dark RGB      | Accessibility Note         |
| :----------------- | :------------ | :------------ | :------------------------- |
| `--text`           | `13 14 19`    | `238 241 247` | WCAG AAA on Surface        |
| `--text-secondary` | `91 93 94`    | `199 205 219` | For subheaders             |
| `--text-muted`     | `138 139 144` | `167 175 194` | For metadata, placeholders |

### 2.4 Semantic Feedback

| Type        | Light RGB    | Dark RGB      | Hex     | Usage         |
| :---------- | :----------- | :------------ | :------ | :------------ |
| **Success** | `22 163 74`  | `34 197 94`   | #16A34A | Success toast |
| **Warning** | `245 158 11` | `251 191 36`  | #F59E0B | Alerts        |
| **Error**   | `239 68 68`  | `248 113 113` | #EF4444 | Form errors   |
| **Info**    | `14 165 233` | `56 189 248`  | #0EA5E9 | Hints         |

### 2.5 Tailwind Config Pattern

```javascript
// tailwind.config.ts
colors: {
  'brand-1': 'rgb(var(--brand-1) / <alpha-value>)',
  // ...
},
boxShadow: {
  'premium': '0 10px 30px -10px rgb(var(--brand-1) / 0.15)', // Dynamic Shadow
}
```

### 2.6 globals.css Pattern

```css
:root {
  --brand-1: 68 119 248;
  --brand-2: 112 68 248;
  --brand-3: 184 68 248;
  --bg: 246 247 247;
  --surface: 255 255 255;
  /* ... etc */
}

.dark {
  --brand-1: 68 119 248;
  --brand-2: 112 68 248;
  --brand-3: 184 68 248;
  --bg: 11 16 32;
  --surface: 15 22 48;
  /* ... etc */
}
```

---

## 3. Visual Effects

### 3.1 Gradients

Used sparingly for emphasis.

- **CTA Gradient**: `linear-gradient(135deg, #4477f8 0%, #7044f8 50%, #b844f8 100%)`
- **Text Gradient (Hero)**: `bg-clip-text text-transparent bg-gradient-to-r from-brand-1 via-brand-2 to-brand-3`
- **Surface Glow**: Subtle glow behind active cards in Dark Mode

### 3.2 Shadows (Depths)

- **Focus Ring**: `ring-4 ring-brand-1/20`
- **Float**: `shadow-xl shadow-brand-1/10` (for sticky elements)

### 3.3 Blur (Glassmorphism)

- Used on **Sticky Header** and **Toast Notifications**
- Class: `backdrop-blur-md bg-surface/80`
