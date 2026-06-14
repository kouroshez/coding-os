import { Controller, Get } from "@nestjs/common";

import { HealthService } from "./health.service.js";

// Thin: delegates to the provider and returns its value (Nest serializes).
@Controller("health")
export class HealthController {
  constructor(private readonly health: HealthService) {}

  @Get()
  check() {
    return this.health.status();
  }
}
