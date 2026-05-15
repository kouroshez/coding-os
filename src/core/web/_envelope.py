"""core.web._envelope — MCP envelope → HTTP response adapter."""

from __future__ import annotations

import json
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# ----- OpenAPI schemas -------------------------------------------------
# Documenting the standard error envelope so generated clients (e.g.
# `openapi-typescript`) emit typed error shapes instead of `unknown`.
class ErrorBody(BaseModel):
    category: str = Field(
        ...,
        description="Error class: validation | permission | not_found | transient | unavailable | internal.",
    )
    message: str = Field(..., description="Human-readable explanation.")
    retryable: bool = Field(False, description="True when the caller may safely retry after a short delay.")


class ErrorEnvelope(BaseModel):
    """Standard error envelope returned for all 4xx/5xx responses."""

    error: ErrorBody


# Reusable `responses=` block — apply to any route that returns the
# envelope error shape (i.e. anything that goes through unwrap()).
ENVELOPE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope, "description": "Validation error."},
    404: {"model": ErrorEnvelope, "description": "Resource not found."},
    500: {"model": ErrorEnvelope, "description": "Internal error."},
    503: {"model": ErrorEnvelope, "description": "Backend unavailable (retryable)."},
}


_CATEGORY_TO_STATUS: dict[str, int] = {
    "validation": 400,
    "permission": 403,
    "not_found": 404,
    "transient": 503,
    "unavailable": 503,
    "internal": 500,
}


def unwrap(raw: str | dict[str, Any]) -> JSONResponse:
    """Parse an MCP envelope and return the appropriate HTTP response."""
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
