// Vite config for {{PROJECT_NAME}} — SvelteKit plugin only; extend as needed.
import { sveltekit } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
});
