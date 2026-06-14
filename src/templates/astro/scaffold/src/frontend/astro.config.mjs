import { defineConfig } from "astro/config";

// SSG by default — pages render to static HTML with zero client JS.
// API endpoints (pages/api/*.ts) and any client:* island are the only
// surfaces that ship runtime code. Switch to `output: "hybrid"` only when
// a route genuinely needs request-time rendering.
export default defineConfig({
  output: "static",
});
