# ARIA Patterns + Focus Management

The two areas where small mistakes cause big a11y failures. Both have correct patterns; both reward following them exactly.

## The Three Rules of ARIA

1. **Don't use ARIA**. Use semantic HTML (`<button>`, `<nav>`, `<main>`, `<dialog>`) first.
2. **If you must, follow the W3C ARIA Authoring Practices Guide patterns exactly.** Don't invent.
3. **Test with a screen reader.** ARIA is broken without verification.

## Common Patterns — Use These Exactly

### Disclosure Button (Show/Hide Section)

```html
<button
  aria-expanded="false"
  aria-controls="more-info">
  More info
</button>
<div id="more-info" hidden>
  Additional content
</div>
```

JS toggles `aria-expanded` AND `hidden`. SR announces "expanded" / "collapsed".

### Modal Dialog

```html
<dialog
  open
  aria-modal="true"
  aria-labelledby="dlg-title"
  aria-describedby="dlg-desc">
  <h2 id="dlg-title">Confirm delete</h2>
  <p id="dlg-desc">This action cannot be undone.</p>
  <button>Cancel</button>
  <button>Delete</button>
</dialog>
```

The native `<dialog>` element handles modal semantics + Esc + backdrop click. Use it instead of div-with-overlay where possible.

### Tabs (W3C APG pattern)

```html
<div role="tablist" aria-label="Account">
  <button role="tab" aria-selected="true"  aria-controls="tab1-panel" id="tab1" tabindex="0">Profile</button>
  <button role="tab" aria-selected="false" aria-controls="tab2-panel" id="tab2" tabindex="-1">Security</button>
</div>
<div role="tabpanel" id="tab1-panel" aria-labelledby="tab1">...</div>
<div role="tabpanel" id="tab2-panel" aria-labelledby="tab2" hidden>...</div>
```

Keyboard:

- **Tab** → moves into / out of the tablist.
- **Arrow Left / Right** → moves between tabs (with `tabindex` rotation).
- **Home / End** → first / last tab.
- **Enter / Space** → activate (or auto-activate on focus, your choice — auto is more common in 2026).

### Combobox (Autocomplete)

This is the gnarliest. Use a library: `react-aria` (Adobe), `headlessui`, `radix-ui`. Don't roll your own.

If you must, follow the APG combobox pattern exactly: <https://www.w3.org/WAI/ARIA/apg/patterns/combobox/>

### Menu (Context Menu / Dropdown)

```html
<button
  aria-haspopup="menu"
  aria-expanded="false"
  aria-controls="actions-menu">
  Actions
</button>
<ul role="menu" id="actions-menu" hidden>
  <li role="menuitem"><a href="/edit">Edit</a></li>
  <li role="menuitem"><a href="/delete">Delete</a></li>
</ul>
```

Keyboard: Down arrow opens; arrows navigate; Esc closes.

### Live Regions

For dynamic updates (toast, status change, search results count) without moving focus:

```html
<!-- Polite: SR finishes current sentence first. -->
<div role="status" aria-live="polite">3 results found</div>

<!-- Assertive: SR interrupts. Use sparingly — for errors/alerts. -->
<div role="alert" aria-live="assertive">Failed to save</div>
```

The element MUST exist on initial render (empty); update its text content. Adding the element AND content at the same time is missed by some SR.

### Loading States

```html
<button aria-busy="true" aria-describedby="status">Save</button>
<span id="status" role="status" aria-live="polite">Saving…</span>
```

SR announces "Saving…" without losing focus.

## Focus Management — Patterns

### Modal Open / Close

```typescript
const previousFocus = useRef<HTMLElement | null>(null);
const dialogRef = useRef<HTMLDialogElement>(null);

function open() {
  previousFocus.current = document.activeElement as HTMLElement;
  dialogRef.current?.showModal();
  // Focus the first interactive element OR the dialog itself.
  const first = dialogRef.current?.querySelector<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  first?.focus();
}

function close() {
  dialogRef.current?.close();
  previousFocus.current?.focus();
  previousFocus.current = null;
}
```

Native `<dialog>` does Esc + backdrop dismiss for free. Use it.

### Focus Trap

In a modal, Tab + Shift+Tab must cycle within the dialog. Native `<dialog open>` handles this automatically. For custom overlays, use `focus-trap-react` or `react-focus-lock`.

```tsx
import FocusTrap from 'focus-trap-react';

{isOpen && (
  <FocusTrap focusTrapOptions={{ escapeDeactivates: true, onDeactivate: close }}>
    <div role="dialog" aria-modal="true">
      ...
    </div>
  </FocusTrap>
)}
```

### Route Change

In a SPA, the browser doesn't announce a navigation. Move focus to the new page:

```tsx
function Page({ title }: { title: string }) {
  const h1Ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    h1Ref.current?.focus();
  }, []);
  return <h1 ref={h1Ref} tabIndex={-1}>{title}</h1>;
}
```

`tabIndex={-1}` lets the element receive focus programmatically without entering the tab order.

Or announce via live region:

```tsx
const { setAnnouncement } = useAnnouncer();
useEffect(() => {
  setAnnouncement(`Navigated to ${title}`);
}, [title]);
```

### Form Submit Error

```typescript
async function onSubmit(data) {
  try {
    await submit(data);
  } catch (err) {
    setErrors(err.fields);
    // Focus the first invalid field (or the error summary).
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      // OR: errorSummaryRef.current?.focus();
    });
  }
}
```

Use `requestAnimationFrame` so focus moves AFTER the DOM update.

### Async Content Load

```tsx
{isLoading ? (
  <p role="status" aria-live="polite">Loading lessons…</p>
) : (
  <ul>{...}</ul>
)}
```

SR announces "Loading lessons…" without focus jump. When loaded, the list becomes available; user can navigate to it via headings.

## React Native — Focus Management

```tsx
import { AccessibilityInfo, findNodeHandle, View } from 'react-native';

const ref = useRef<View>(null);

useEffect(() => {
  if (isModalOpen) {
    const reactTag = findNodeHandle(ref.current);
    if (reactTag) AccessibilityInfo.setAccessibilityFocus(reactTag);
  }
}, [isModalOpen]);

<View ref={ref} accessible={true} accessibilityLabel="Confirm delete">
  ...
</View>
```

For VoiceOver / TalkBack focus on a specific element after a UI change, `AccessibilityInfo.setAccessibilityFocus(reactTag)` is the API. Do it inside `requestAnimationFrame` or after `InteractionManager.runAfterInteractions`.

## ARIA Don'ts

1. **`role="button"` on a `<button>`** — redundant; remove.
2. **`aria-label="Submit"`** on a button that has visible text "Submit" — redundant; remove.
3. **`aria-hidden="true"`** on a focusable element — SR can't read but tab still lands → confused user. Either hide both or neither.
4. **`tabindex` > 0** — breaks the natural tab order. Use 0 (in order) or -1 (programmatic only).
5. **`role="presentation"`** + interactive children — strips semantics from the parent but children become unreachable.
6. **Multiple `aria-live` regions** firing at once — they queue + interrupt each other.
7. **`role="alert"` for non-urgent updates** — interrupts the SR; only for errors / time-sensitive.
8. **Updating an `aria-live` element by replacing its DOM node** — SR misses the change. Update text content instead.

## Source Material

- *WAI-ARIA Authoring Practices Guide (APG)*: <https://www.w3.org/WAI/ARIA/apg/>
- *Inclusive Components* (Heydon Pickering) — patterns for tabs, modals, menus.
- *react-aria*: <https://react-spectrum.adobe.com/react-aria/> — battle-tested hooks.
- *Headless UI*: <https://headlessui.com/> — pre-built unstyled accessible components.
- *Radix UI*: <https://www.radix-ui.com/> — same idea, slightly different API.
- *focus-trap-react*: <https://github.com/focus-trap/focus-trap-react>
