import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

// Liveness probe for {{PROJECT_NAME}} — GET /health → { status: "ok" }.
export const GET: RequestHandler = () => {
  return json({ status: "ok" });
};
