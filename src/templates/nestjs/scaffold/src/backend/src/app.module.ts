import { Module } from "@nestjs/common";

import { HealthModule } from "./health/health.module.js";

// Root module wires feature modules — it owns no business logic.
@Module({
  imports: [HealthModule],
})
export class AppModule {}
