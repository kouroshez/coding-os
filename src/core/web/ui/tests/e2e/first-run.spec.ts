import { expect, test } from "@playwright/test";

/**
 * First-run path: a visitor with zero registered projects must be able to
 * start one from the panel. Runs against the static build with `/api/**`
 * stubbed, so it covers the shell + routing that component tests mock away.
 */

const EMPTY_REGISTRY = { projects: [], count: 0 };

const STUBS: Record<string, unknown> = {
  "/api/hub/projects": EMPTY_REGISTRY,
  "/api/hub/suggest-roots": { suggestions: ["/code"], scaffoldable: ["/code"] },
  "/api/hub/presets": {
    presets: [
      {
        id: "nextjs-fastapi",
        label: "Next.js + FastAPI full-stack",
        description: "TS frontend + Python API",
        stacks: ["nextjs", "fastapi"],
      },
    ],
  },
  "/api/hub/stacks": {
    stacks: [{ id: "fastapi", label: "FastAPI", category: "backend", language: "python" }],
  },
  "/api/hub/adapters": { adapters: [{ id: "claude", label: "Claude Code" }] },
  "/api/hub/skills": { skills: [] },
  "/api/hub/modules": {
    default_profile: "standard",
    default_disabled: ["cognition"],
    modules: [
      { id: "kernel", label: "Kernel — lifecycle", kernel: true, depends_on: [] },
      { id: "graph", label: "Knowledge graph — queries", kernel: false, depends_on: [] },
      { id: "cognition", label: "Cognition — role chains", kernel: false, depends_on: [] },
    ],
  },
};

// Shell widgets (agent presence, live status) read collections they expect to
// exist; an empty-object fallback would crash the render before the page under
// test appears, so unstubbed endpoints answer with an empty-of-everything body.
const EMPTY_COLLECTIONS = {
  projects: [],
  count: 0,
  items: [],
  agents: [],
  sessions: [],
  modules: [],
  stacks: [],
  adapters: [],
  skills: [],
  presets: [],
  suggestions: [],
  scaffoldable: [],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = STUBS[path] ?? EMPTY_COLLECTIONS;
    await route.fulfill({ status: 200, json: { data: body, meta: { layer: "hub" } } });
  });
});

test("zero projects: the empty state offers creating one, not just importing", async ({ page }) => {
  await page.goto("/");
  const empty = page.getByText("Start your first project");
  await expect(empty).toBeVisible();

  // The create path must be reachable without the CLI (ADR-0007).
  const createCta = page.getByRole("button", { name: "New project" }).last();
  await createCta.click();
  await expect(page.getByRole("heading", { name: "Create a new project" })).toBeVisible();
});

test("composer chips start from the default profile, not an all-on fiction", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "New project" }).last().click();
  await page.getByRole("button", { name: /Advanced/ }).click();

  await expect(page.getByTestId("module-cognition")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("module-graph")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("module-kernel")).toBeDisabled();
});
