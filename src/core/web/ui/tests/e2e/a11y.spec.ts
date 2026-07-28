import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Accessibility smoke suite for the Hub UI.
 *
 * Scans the static build (served by `vite preview`) with axe-core
 * against WCAG 2.1 A + AA rule sets. The goal is a *floor*: no
 * serious/critical violations on the routes a first-time visitor
 * lands on. Data-dependent component states are out of scope here —
 * they belong in component tests with mocked `/api` responses.
 */

/**
 * `vite preview` serves the bundle with no FastAPI behind it, so every /api
 * call would hang and `networkidle` would never settle. Stub the API and wait
 * for the shell instead — the scan is about markup, not data.
 */
const API_STUB = { projects: [], count: 0, agents: [], items: [], suggestions: [], modules: [] };

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 200, json: { data: API_STUB, meta: { layer: "hub" } } }));
});

const ROUTES: { name: string; path: string }[] = [
  { name: "home / project picker", path: "/" },
  { name: "need-project landing", path: "/board" },
];

for (const route of ROUTES) {
  test(`a11y: ${route.name} has no serious/critical violations`, async ({ page }) => {
    await page.goto(route.path);
    await page.locator("header").first().waitFor();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );

    // Attach a readable summary when this fails.
    if (blocking.length > 0) {
      const summary = blocking
        .map((v) => `  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`)
        .join("\n");
      expect(blocking, `axe violations on ${route.path}:\n${summary}`).toEqual([]);
    } else {
      expect(blocking).toEqual([]);
    }
  });
}

test("a11y: document has a lang attribute", async ({ page }) => {
  await page.goto("/");
  const lang = await page.getAttribute("html", "lang");
  expect(lang, "the <html> element must declare a lang attribute").toBeTruthy();
});

test("a11y: a single top-level landmark / main region exists", async ({ page }) => {
  await page.goto("/");
  await page.locator("header").first().waitFor();
  // Either a <main> element or an explicit role=main.
  const mainCount = await page.locator("main, [role='main']").count();
  expect(mainCount).toBeGreaterThanOrEqual(1);
});
