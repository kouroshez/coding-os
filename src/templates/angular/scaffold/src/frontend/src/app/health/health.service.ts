import { Injectable, signal } from "@angular/core";

// Injectable service — owns state (signals) and side effects, so the
// component stays presentation-only and the service is testable in isolation.
@Injectable({ providedIn: "root" })
export class HealthService {
  private readonly _status = signal<string>("ok");

  readonly status = this._status.asReadonly();
}
