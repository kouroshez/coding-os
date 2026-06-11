// Minimal Nuxt 3 config — extend as the app grows ({{PROJECT_NAME}}).
export default defineNuxtConfig({
  devtools: { enabled: true },
});

// Pre-install ambient declaration so editors/tsc don't error before
// `npm install` generates .nuxt/tsconfig (real types shadow this).
declare global {
  function defineNuxtConfig(config: Record<string, unknown>): Record<string, unknown>;
}
export {};
