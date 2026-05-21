import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the Hub UI accessibility suite.
 *
 * The a11y spec scans the *static build* served by `vite preview` —
 * this exercises the shell, navigation, and landing pages without
 * needing the FastAPI backend. Component states that require live
 * `/api` data are out of scope for the static scan.
 *
 * Run:  npm run build && npm run test:a11y
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Serve the production build; Playwright waits for it before testing.
  webServer: {
    command: "npm run preview -- --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
