import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: { url: 'http://127.0.0.1:9188/' },
    },
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      // Measure the app, not the harness: generated API types, test files and
      // entrypoints carry no branches a test could meaningfully cover.
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/lib/api-types.ts',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      // The measurement, minus one point: v8 attributes a few lines
      // differently between local Node and the 22 CI pins, and a gate that
      // reddens on an unchanged tree gets switched off. Raise these when the
      // number rises — never lower them to make a red run pass.
      thresholds: {
        lines: 32,
        statements: 30,
        functions: 27,
        branches: 25,
      },
    },
  },
});
