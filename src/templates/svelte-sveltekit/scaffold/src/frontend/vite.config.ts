// Vite config for {{PROJECT_NAME}} — SvelteKit plugin only; extend as needed.
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
});
