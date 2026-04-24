import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

// Vite config for coding-os SPA.
// - Dev server: http://127.0.0.1:5173 (strict port).
// - /api/* proxied to FastAPI backbone on http://127.0.0.1:9188 (stable port).
// - Build output: dist/ (served by FastAPI StaticFiles in production).
//
// Port choice — the backend and SPA share a single, bookmarkable public URL
// (port 9188) so the board is always reachable at the same place across runs.
const BACKEND_ORIGIN = 'http://127.0.0.1:9188';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': { target: BACKEND_ORIGIN, changeOrigin: true },
      '/health': { target: BACKEND_ORIGIN, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 900,
  },
});
