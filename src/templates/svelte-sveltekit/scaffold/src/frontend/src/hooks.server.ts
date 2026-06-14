import type { HandleServerError } from "@sveltejs/kit";

// The single central error shaper for {{PROJECT_NAME}}. SvelteKit calls this
// for every unexpected server error; the returned object is the only error
// surface a client ever sees (shape: docs/api-contracts/error-format.md).
// Log full detail server-side; never leak internals to the response.
export const handleError: HandleServerError = ({ error, status, message }) => {
  const reference = crypto.randomUUID();
  console.error(`[{{PROJECT_NAME}}] error ${reference} (${status})`, error);
  return {
    message: status < 500 ? message : "Internal error",
    reference,
  };
};
