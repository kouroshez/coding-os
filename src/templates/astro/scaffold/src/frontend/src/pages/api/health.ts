import type { APIRoute } from "astro";

import { problem } from "../../lib/problem";

// API endpoint — GET only. Success returns a thin JSON body; anything else
// is shaped by the single problem() helper so every error response matches.
export const GET: APIRoute = () =>
  new Response(JSON.stringify({ status: "ok" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

export const ALL: APIRoute = () => problem(405, "Method Not Allowed");
