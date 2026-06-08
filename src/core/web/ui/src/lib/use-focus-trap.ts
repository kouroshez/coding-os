import { useEffect } from 'react';
import type { RefObject } from 'react';

/**
 * Trap keyboard focus inside an open overlay and wire Esc-to-close +
 * scroll-lock + focus-restore. The ONE implementation shared by the Modal
 * primitive and the board task-detail drawer (which keeps its own board
 * token styling but must satisfy the same dialog a11y contract).
 *
 * Listens on `document` so Esc fires regardless of which child holds focus;
 * Tab/Shift+Tab cycle within `ref`. No-op while `active` is false.
 */

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function useFocusTrap(
  ref: RefObject<HTMLElement | null>,
  { active, onClose }: { active: boolean; onClose?: () => void },
): void {
  useEffect(() => {
    if (!active) return undefined;

    const restore = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const node = ref.current;
    const firstFocusable = node?.querySelector<HTMLElement>(FOCUSABLE);
    (firstFocusable ?? node)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose?.();
        return;
      }
      if (e.key !== 'Tab') return;
      const root = ref.current;
      if (!root) return;
      const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const activeEl = document.activeElement;
      if (e.shiftKey && activeEl === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && activeEl === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      restore?.focus?.();
    };
  }, [active, onClose, ref]);
}
