"""core.web._envelope — MCP envelope → HTTP response adapter."""

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
