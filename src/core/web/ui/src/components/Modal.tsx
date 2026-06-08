import { useCallback, useEffect, useRef } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, ReactNode } from 'react';

/**
 * Shared centered modal dialog — the ONE accessible overlay primitive the
 * Hub reuses (board task-detail, agent-detail, project wizard). No external
 * dep (radix is not installed). Owns: centered geometry, backdrop, focus
 * trap, Esc-to-close, scroll-lock, focus restore, and dialog a11y semantics.
 *
 * Consumers pass the body + optional title/footer; they never re-implement
 * the overlay so every modal looks and behaves identically.
 */

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

const WIDTHS = { sm: '28rem', md: '40rem', lg: '56rem', xl: '72rem' } as const;

export function Modal({
  open,
  onClose,
  title,
  titleId = 'cos-modal-title',
  size = 'lg',
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  titleId?: string;
  size?: keyof typeof WIDTHS;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const card = cardRef.current;
    const first = card?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? card)?.focus();

    return () => {
      document.body.style.overflow = prevOverflow;
      restoreRef.current?.focus?.();
    };
  }, [open]);

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const card = cardRef.current;
      if (!card) return;
      const items = Array.from(card.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  if (!open) return null;

  const onBackdrop = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-[200] grid place-items-center p-4"
      role="presentation"
      onMouseDown={onBackdrop}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[rgba(8,10,14,0.62)] backdrop-blur-sm" />
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        style={{ maxWidth: WIDTHS[size] }}
        className="relative z-10 flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-2xl focus:outline-none"
      >
        {title && (
          <div className="flex shrink-0 items-center justify-between gap-4 border-b border-[var(--cos-border)] px-6 py-4">
            <h2 id={titleId} className="truncate text-base font-semibold tracking-tight text-[var(--cos-text)]">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1 text-[var(--cos-muted)] transition-colors hover:bg-white/5 hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-auto px-6 py-5">{children}</div>
        {footer && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[var(--cos-border)] px-6 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
