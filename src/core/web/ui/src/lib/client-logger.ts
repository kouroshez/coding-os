// Browser-side error reporting. Mirrors every captured failure to the devtools
// console (local visibility) AND beacons it to POST /api/logs/client, which
// logging_os routes into the same cos.log.jsonl sink as server logs — so a
// broken SPA is never silent. Fire-and-forget: logging must never throw or block
// the app, so every path here swallows its own errors.

import { csrfHeader, resolveApiUrl } from './api-client';

export type ClientLogLevel = 'debug' | 'info' | 'warn' | 'error';

function normalizeContext(ctx: unknown): unknown {
  if (ctx === undefined) return undefined;
  if (ctx instanceof Error) return { name: ctx.name, message: ctx.message, stack: ctx.stack };
  if (typeof ctx === 'object' && ctx !== null) {
    try {
      return JSON.parse(JSON.stringify(ctx));
    } catch {
      return String(ctx);
    }
  }
  return ctx;
}

/**
 * Report a browser-side log/error to the server sink (and the console). Never
 * throws. `level` defaults to 'error' since this is primarily an error beacon.
 */
export function reportClientError(
  message: string,
  context?: unknown,
  level: ClientLogLevel = 'error',
): void {
  // Local visibility first — devtools still works even if the beacon fails.
  if (level === 'error') console.error('[hub]', message, context ?? '');
  else if (level === 'warn') console.warn('[hub]', message, context ?? '');

  try {
    void fetch(resolveApiUrl('/api/logs/client'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...csrfHeader() },
      body: JSON.stringify({
        level,
        message: String(message).slice(0, 2000),
        url: typeof window !== 'undefined' ? window.location.href : '',
        context: normalizeContext(context),
      }),
      keepalive: true, // survive a navigation/unload so the beacon still lands
    }).catch(() => {
      /* server unreachable — the console line above is the fallback */
    });
  } catch {
    /* never let logging break the caller */
  }
}

let installed = false;

/**
 * Capture EVERY uncaught error + unhandled promise rejection in the SPA exactly
 * once, beaconing each to the server. Call once at app startup.
 */
export function installGlobalErrorReporting(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  window.addEventListener('error', (e: ErrorEvent) => {
    reportClientError(e.message || 'uncaught error', {
      filename: e.filename,
      lineno: e.lineno,
      colno: e.colno,
      stack: e.error instanceof Error ? e.error.stack : undefined,
    });
  });

  window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    const reason = e.reason;
    reportClientError(
      reason instanceof Error ? reason.message : 'unhandled promise rejection',
      reason instanceof Error ? { stack: reason.stack } : { reason: String(reason) },
    );
  });
}
