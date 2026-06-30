const CODE_BY_STATUS: Record<number, string> = {
  400: "VALIDATION_ERROR",
  401: "UNAUTHORIZED",
  403: "FORBIDDEN",
  404: "NOT_FOUND",
  405: "METHOD_NOT_ALLOWED",
  409: "CONFLICT",
  422: "UNPROCESSABLE_ENTITY",
  429: "RATE_LIMITED",
  503: "SERVICE_UNAVAILABLE",
};

export interface ErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}

export function problem(status: number, message: string): Response {
  const code = CODE_BY_STATUS[status] ?? "INTERNAL_ERROR";
  const body: ErrorBody = {
    error: { code, message, request_id: crypto.randomUUID() },
  };
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
