import {
  ApplicationConfig,
  ErrorHandler,
  provideBrowserGlobalErrorListeners,
} from "@angular/core";
import { provideHttpClient } from "@angular/common/http";
import { provideRouter } from "@angular/router";

import { GlobalErrorHandler } from "./core/global-error-handler";
import { routes } from "./app.routes";

// The DI root — wires application-wide providers only, no logic.
// Zoneless by default (no zone.js); the global ErrorHandler is the
// ONLY error-response shaper.
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(),
    { provide: ErrorHandler, useClass: GlobalErrorHandler },
  ],
};
