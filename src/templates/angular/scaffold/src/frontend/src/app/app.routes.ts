import { Routes } from "@angular/router";

import { HealthComponent } from "./health/health.component";

// Standalone routes — lazy-load feature components as the app grows.
export const routes: Routes = [
  { path: "", component: HealthComponent },
];
