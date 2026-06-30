// Vitest config for {{PROJECT_NAME}} unit tests — kept separate from
// vite.config.ts so the SvelteKit plugin (which needs the generated
// .svelte-kit/ dir) is not loaded for pure unit runs.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.{test,spec}.ts"],
  },
});
