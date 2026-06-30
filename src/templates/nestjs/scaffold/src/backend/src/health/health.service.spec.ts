import "reflect-metadata";

import { Test } from "@nestjs/testing";
import { describe, expect, it } from "vitest";

import { HealthService } from "./health.service.js";

// Transport-free unit test of the existing HealthService for {{PROJECT_NAME}}.
// Built through the Nest testing module (no HTTP, no bound port) per the nestjs
// skill's Testing contract; the provider is the only layer that thinks.
describe("HealthService", () => {
  it("reports an ok status with no dependencies", async () => {
    const moduleRef = await Test.createTestingModule({
      providers: [HealthService],
    }).compile();

    const service = moduleRef.get(HealthService);

    expect(service.status()).toEqual({ status: "ok" });
  });
});
