import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

// Vite config for coding-os SPA.
// - Dev server: http://localhost:5173
// - /api/* proxied to FastAPI backbone on http://127.0.0.1:4748 (S4).
// - Build output: dist/ (served by FastAPI StaticFiles when present).
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
      '/api': {
        target: 'http://127.0.0.1:4748',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:4748',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 900,
  },
});
