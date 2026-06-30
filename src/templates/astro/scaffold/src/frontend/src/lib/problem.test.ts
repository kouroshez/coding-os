import { describe, expect, it } from "vitest";

import { ALL, GET } from "../pages/api/health";
import { problem } from "./problem";

describe("problem", () => {
  it("shapes the canonical error envelope with code, message, and request_id", async () => {
    const res = problem(405, "Method Not Allowed");

    expect(res.status).toBe(405);
    expect(res.headers.get("content-type")).toBe("application/json");
    const body = await res.json();
    expect(body.error.code).toBe("METHOD_NOT_ALLOWED");
    expect(body.error.message).toBe("Method Not Allowed");
    expect(typeof body.error.request_id).toBe("string");
    expect(body.error.request_id.length).toBeGreaterThan(0);
  });
});

describe("health endpoint", () => {
  it("GET returns a thin ok body", async () => {
    const res = await GET({} as never);

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/json");
    await expect(res.json()).resolves.toEqual({ status: "ok" });
  });

  it("ALL (non-GET) returns the canonical 405 error envelope", async () => {
    const res = await ALL({} as never);

    expect(res.status).toBe(405);
    expect(res.headers.get("content-type")).toBe("application/json");
    const body = await res.json();
    expect(body.error.code).toBe("METHOD_NOT_ALLOWED");
    expect(body.error.message).toBe("Method Not Allowed");
    expect(typeof body.error.request_id).toBe("string");
  });
});
