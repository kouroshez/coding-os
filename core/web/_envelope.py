"""core.web._envelope — MCP envelope → HTTP response adapter.

PURPOSE: Convert the cos_* tool envelope ({ok, data, error}) into a proper
         FastAPI JSONResponse, mapping error categories to HTTP status codes
         and preserving `meta` inside the response body as {data, meta}.
INPUT:   raw: str or dict — the MCP tool envelope (JSON string or parsed dict).
OUTPUT:  FastAPI Response (200 with {data, meta} on ok, 4xx/5xx on error).
DEPENDENCIES: fastapi, json.
NOTES:  The body-level wrapping {data: ..., meta: ...} is cleaner than a
        custom header for frontend consumption (no CORS preflight surprises).
        Error category → HTTP status mapping follows CLAUDE.md Rule 13.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.responses import JSONResponse


_CATEGORY_TO_STATUS: dict[str, int] = {
    "validation": 400,
    "permission": 403,
    "not_found": 404,
    "transient": 503,
    "unavailable": 503,
    "internal": 500,
}


def unwrap(raw: str | dict[str, Any]) -> JSONResponse:
    """Parse an MCP envelope and return the appropriate HTTP response.

    PURPOSE: Single chokepoint that converts MCP tool responses to HTTP.
    INPUT:   raw — JSON string from a cos_* tool, or an already-parsed dict.
    OUTPUT:  JSONResponse — 200 with {data, meta} on success;
             4xx/5xx with {error} on failure.
    DEPENDENCIES: json, fastapi.responses.JSONResponse.
    NOTES:   Preserves meta at body level so the SPA can read pagination
             info without custom header parsing.
    """
    if isinstance(raw, str):
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=500,
                content={"error": {"category": "internal", "message": "invalid tool response"}},
            )
    else:
        envelope = raw

    if envelope.get("ok"):
        payload = envelope.get("data", {})
        if isinstance(payload, dict):
            meta = payload.pop("meta", None)
            return JSONResponse(
                status_code=200,
                content={"data": payload, "meta": meta},
            )
        return JSONResponse(status_code=200, content={"data": payload, "meta": None})

    error = envelope.get("error", {})
    category = error.get("category", "internal")
    status_code = _CATEGORY_TO_STATUS.get(category, 500)
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
    )
