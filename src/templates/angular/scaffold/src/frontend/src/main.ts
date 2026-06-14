import { bootstrapApplication } from "@angular/platform-browser";

import { AppComponent } from "./app/app.component";
import { appConfig } from "./app/app.config";

// Entry point — no logic. Providers live in appConfig (the DI root).
bootstrapApplication(AppComponent, appConfig).catch((err) =>
  console.error("{{PROJECT_NAME}} failed to bootstrap", err),
);
