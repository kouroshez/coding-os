// The ONLY error-response shaper for API endpoints (RFC 9457 problem shape,
// per docs/api-contracts/error-format.md). Endpoints throw/return through
// this helper; full detail goes to the server log, never to the client.

export interface Problem {
  type: string;
  title: string;
  status: number;
}

export function problem(status: number, title: string): Response {
  const body: Problem = { type: "about:blank", title, status };
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}
