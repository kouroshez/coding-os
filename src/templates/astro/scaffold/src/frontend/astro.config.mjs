import { defineConfig } from "astro/config";

// SSG by default — pages render to static HTML with zero client JS.
// API endpoints (pages/api/*.ts) and any client:* island are the only
// surfaces that ship runtime code. For a route that needs request-time
// rendering, add `export const prerender = false` to it (and an adapter),
// or set `output: "server"` when most routes are dynamic.
export default defineConfig({
  output: "static",
});
