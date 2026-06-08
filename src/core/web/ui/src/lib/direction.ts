// App-level text-direction seam (TASK-251). The Hub is LTR by default but
// RTL-ready: flipping the whole UI is config (VITE_HUB_DIR=rtl), not a rewrite.
// index.css already ships [dir="rtl"] + the Vazirmatn font; primitives use
// logical Tailwind utilities that mirror automatically. User/agent prose uses
// dir="auto" so a Persian message renders RTL even while the chrome stays LTR.

export type HubDir = 'ltr' | 'rtl';

/** Normalize any raw config string to a valid dir; anything but 'rtl' is 'ltr'. */
export function resolveHubDir(raw?: string | null): HubDir {
  return String(raw ?? '').trim().toLowerCase() === 'rtl' ? 'rtl' : 'ltr';
}

/**
 * Set <html dir/lang> from VITE_HUB_DIR (default ltr). Called once from
 * main.tsx. `raw`/`doc` are injectable for tests.
 */
export function applyHubDirection(raw?: string | null, doc: Document = document): HubDir {
  const fromEnv = (import.meta.env?.VITE_HUB_DIR as string | undefined) ?? null;
  const dir = resolveHubDir(raw ?? fromEnv);
  doc.documentElement.setAttribute('dir', dir);
  return dir;
}
