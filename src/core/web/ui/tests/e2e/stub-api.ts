import type { Page } from "@playwright/test";

/**
 * `vite preview` serves the built bundle with no FastAPI behind it, so every
 * /api call would hang and the shell would crash on missing collections.
 * Both specs stub through here so they cannot drift into different empties.
 */
export const EMPTY_COLLECTIONS = {
  projects: [],
  count: 0,
  items: [],
  agents: [],
  sessions: [],
};

export async function stubApi(page: Page, routes: Record<string, unknown> = {}) {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = routes[path] ?? EMPTY_COLLECTIONS;
    return route.fulfill({ status: 200, json: { data: body, meta: { layer: "hub" } } });
  });
}
