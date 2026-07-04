import { TestBed } from "@angular/core/testing";

import { HealthService } from "./health.service";

describe("HealthService", () => {
  let service: HealthService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(HealthService);
  });

  it("exposes an initial 'ok' status signal", () => {
    expect(service.status()).toBe("ok");
  });
});
