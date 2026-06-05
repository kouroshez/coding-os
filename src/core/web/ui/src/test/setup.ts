import '@testing-library/jest-dom/vitest';

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
