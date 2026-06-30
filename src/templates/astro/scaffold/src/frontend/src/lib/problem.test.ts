// Unit test for the {{PROJECT_NAME}} frontend — exercises the single
// problem.ts error shaper (RFC 9457) and the health endpoint handlers.
// Pages/components are gated by `astro check` + `astro build`; pure logic
// like the problem() shaper is covered here. See docs/api-contracts/error-format.md.
import { describe, expect, it } from "vitest";

import { ALL, GET } from "../pages/api/health";
import { problem } from "./problem";

describe("problem", () => {
  it("shapes an RFC 9457 problem body with the given status and title", async () => {
    const res = problem(405, "Method Not Allowed");

    expect(res.status).toBe(405);
    expect(res.headers.get("content-type")).toBe("application/problem+json");
    await expect(res.json()).resolves.toEqual({
      type: "about:blank",
      title: "Method Not Allowed",
      status: 405,
    });
  });
});

describe("health endpoint", () => {
  it("GET returns a thin ok body", async () => {
    const res = GET({} as never);

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/json");
    await expect(res.json()).resolves.toEqual({ status: "ok" });
  });

  it("ALL (non-GET) returns the problem-shaped 405", async () => {
    const res = ALL({} as never);

    expect(res.status).toBe(405);
    expect(res.headers.get("content-type")).toBe("application/problem+json");
    await expect(res.json()).resolves.toEqual({
      type: "about:blank",
      title: "Method Not Allowed",
      status: 405,
    });
  });
});
