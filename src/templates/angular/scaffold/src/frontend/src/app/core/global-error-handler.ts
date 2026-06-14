import { ErrorHandler, Injectable } from "@angular/core";

// The ONLY place that shapes an unhandled error (parallel to a backend's
// global exception filter). Logs full detail; UI surfaces a generic message
// and never renders a raw server/stack string to the user.
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  handleError(error: unknown): void {
    const detail = error instanceof Error ? error.stack ?? error.message : String(error);
    console.error("[{{PROJECT_NAME}}] unhandled error:", detail);
  }
}
