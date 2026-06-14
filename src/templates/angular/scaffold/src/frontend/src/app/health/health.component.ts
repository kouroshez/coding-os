import { Component, ChangeDetectionStrategy, inject } from "@angular/core";

import { HealthService } from "./health.service";

// Standalone, presentation-only: reads a signal from the service and renders.
@Component({
  selector: "app-health",
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<p role="status">status: {{ health.status() }}</p>`,
})
export class HealthComponent {
  protected readonly health = inject(HealthService);
}
