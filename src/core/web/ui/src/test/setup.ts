import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// findBy*/waitFor default to a 1s budget, which is a machine-speed assertion
// nobody wrote on purpose. Observed once across ten full-suite runs:
// NeedProjectPage.routing timed out waiting for a button behind a resolved
// fetch, while passing 8/8 in isolation. These tests assert behaviour, not
// latency; 5s costs a passing run nothing and only delays a real failure.
configure({ asyncUtilTimeout: 5000 });

// jsdom in this vitest config ships without localStorage — provide an
// in-memory shim so storage-backed stores (theme-store) load + assert.
if (typeof window !== 'undefined' && !window.localStorage) {
  const mem: Record<string, string> = {};
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => (k in mem ? mem[k] : null),
      setItem: (k: string, v: string) => {
        mem[k] = String(v);
      },
      removeItem: (k: string) => {
        delete mem[k];
      },
      clear: () => {
        for (const k of Object.keys(mem)) delete mem[k];
      },
    },
  });
}

// jsdom ships no EventSource; a real browser has one. Provide a no-op stub so
// components that open a shared SSE connection in an effect (e.g. TraceTimeline)
// don't crash tests that don't care about the stream. Tests that assert SSE
// behaviour still override globalThis.EventSource (see shared-event-source.test.ts).
if (typeof globalThis.EventSource === 'undefined') {
  class StubEventSource {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readyState = 1;
    constructor(_url: string) {}
    addEventListener(): void {}
    removeEventListener(): void {}
    close(): void {}
  }
  globalThis.EventSource = StubEventSource as unknown as typeof EventSource;
}
