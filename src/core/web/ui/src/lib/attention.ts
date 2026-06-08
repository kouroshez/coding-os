// Attention model helpers (TASK-252). Pure where possible so the tab-title and
// event-summary logic is unit-tested; the favicon dot is a guarded DOM side
// effect (no-op when canvas is unavailable, e.g. jsdom).

export const ATTENTION_BASE_TITLE = 'Coding OS Hub';

/** Tab title with an unread-count prefix: "(3) Coding OS Hub" / "Coding OS Hub". */
export function formatTabTitle(count: number, base: string = ATTENTION_BASE_TITLE): string {
  return count > 0 ? `(${count}) ${base}` : base;
}

/** Human one-liner for an attention SSE event — what the human reads in the feed/notification. */
export function summarizeStreamEvent(type: string, data: unknown): string {
  const d = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
  switch (type) {
    case 'dispatch-completed': {
      const formula = String(d.formula_id ?? 'agent');
      const status = String(d.status ?? 'ok');
      return status === 'ok' ? `${formula} finished` : `${formula} ${status}`;
    }
    case 'agent-blocked':
      return d.reason ? `Agent blocked: ${String(d.reason)}` : 'Agent blocked';
    case 'needs-input':
      return 'Agent needs your input';
    default:
      return type;
  }
}

let _originalFavicon: string | null = null;

function _faviconLink(): HTMLLinkElement | null {
  if (typeof document === 'undefined') return null;
  let link = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  if (_originalFavicon === null) _originalFavicon = link.getAttribute('href') ?? '';
  return link;
}

/** Toggle a small alert dot on the favicon. Guarded — silently no-ops without canvas. */
export function setFaviconDot(on: boolean): void {
  const link = _faviconLink();
  if (!link) return;
  try {
    if (!on) {
      if (_originalFavicon) link.setAttribute('href', _originalFavicon);
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = 32;
    canvas.height = 32;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#0b0d12';
    ctx.fillRect(0, 0, 32, 32);
    ctx.beginPath();
    ctx.arc(22, 10, 8, 0, Math.PI * 2);
    ctx.fillStyle = '#f0883e';
    ctx.fill();
    link.setAttribute('href', canvas.toDataURL('image/png'));
  } catch {
    // canvas unavailable (jsdom / locked-down env) — title badge still signals.
  }
}
