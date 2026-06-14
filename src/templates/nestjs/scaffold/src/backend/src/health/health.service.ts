import { Injectable } from "@nestjs/common";

// Transport-free provider — no @Req/@Res, so it is unit-testable in isolation.
@Injectable()
export class HealthService {
  status(): { status: string } {
    return { status: "ok" };
  }
}
