// Sample route test for {{PROJECT_NAME}} ({{DATE}}) — exercises the shipped
// healthRouter via supertest in-memory, never binding a real port
// (docs/playbooks/express-service.md: test through the factory, no app.listen).
import assert from "node:assert/strict";
import { test } from "node:test";

import express from "express";
import request from "supertest";

import { healthRouter } from "./health.js";

// Mirror index.ts's createApp() mount, minus the listen() side effect, so the
// test drives the SAME router the running service mounts at /health.
function buildTestApp() {
  const app = express();
  app.use(express.json());
  app.use("/health", healthRouter);
  return app;
}

test("GET /health returns 200 with status ok", async () => {
  const res = await request(buildTestApp()).get("/health");

  assert.equal(res.status, 200);
  assert.deepEqual(res.body, { status: "ok" });
});

test("unknown method on /health is not served by the router (404)", async () => {
  // The health router only registers GET "/"; a DELETE falls through unhandled.
  const res = await request(buildTestApp()).delete("/health");

  assert.equal(res.status, 404);
});
