// Minimal SvelteKit config — extend as the app grows ({{PROJECT_NAME}}).
import adapter from "@sveltejs/adapter-auto";

/** @type {import('@sveltejs/kit').Config} */
export default {
  kit: {
    // $lib resolves to src/lib by default; routes live under src/routes.
    adapter: adapter(),
  },
};
