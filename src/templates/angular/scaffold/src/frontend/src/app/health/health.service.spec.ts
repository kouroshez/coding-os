import { TestBed } from "@angular/core/testing";

import { HealthService } from "./health.service";

// Sample unit test — proves `ng test` (the @angular/build:unit-test builder
// on Vitest + jsdom) runs green day-one. Services stay presentation-free, so
// they are testable in isolation with no TestBed component fixture.
describe("HealthService", () => {
  beforeEach(() => TestBed.configureTestingModule({}));

  it("reports ok status", () => {
    const service = TestBed.inject(HealthService);

    expect(service.status()).toBe("ok");
  });
});
