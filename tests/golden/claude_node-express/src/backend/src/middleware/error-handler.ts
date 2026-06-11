import type { NextFunction, Request, Response } from "express";

// The ONLY place that shapes error responses (docs/api-contracts/error-format.md).
export function errorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  _next: NextFunction,
): void {
  console.error(err); // full detail to the log, never to the client
  res.status(500).json({ title: "Internal Server Error", status: 500 });
}
