"""Codex dispatch prompt + output-schema composition.

Split out of sdk_dispatcher.py when that file crossed the 500-line backstop.
The seam is cohesive on its own terms: everything here turns a DispatchRequest
into the text and JSON schema the codex CLI is handed, and none of it touches
process lifecycle, backend selection, or result mapping.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from thinking_os.dispatcher import DispatchRequest
from thinking_os.dispatcher_helpers import render_shared_context

logger = logging.getLogger(__name__)


def _dispatch_context(request: DispatchRequest) -> str:
    # Codex dispatch runs --sandbox read-only with mcp_servers={}, so this prompt
    # is the child's ONLY channel to shared state — it cannot look anything up.
    work_context = render_shared_context(getattr(request, "shared_context", None))
    return (
        (f"{work_context}\n\n" if work_context else "") + "## Dispatch Context\n"
        f"- Formula: {request.formula_id}\n"
        f"- Persona: {request.persona_id or 'n/a'}\n"
        f"- Intensity: {request.intensity}\n\n"
        "## Input Context (upstream formulas only)\n"
        f"```json\n{json.dumps(request.input_slice, ensure_ascii=False, indent=2, default=str)}\n```\n\n"
        "## Task\n"
        f"{request.prompt}\n\n"
        "Produce the EvidenceBundle slice for this formula as a single "
        "```json ... ``` block at the end of your response."
    )


def _cli_prompt(system_body: str, request: DispatchRequest) -> str:
    return f"{system_body}\n\n{_dispatch_context(request)}"


def _jsonable(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalize_strict_schema(value: Any) -> bool:
    if isinstance(value, list):
        return all(_normalize_strict_schema(item) for item in value)
    if not isinstance(value, dict):
        return True

    if value.get("type") == "object":
        properties = value.get("properties")
        required = value.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            return False
        if value.get("additionalProperties") not in (None, False):
            return False
        if set(required) != set(properties):
            return False
        value["additionalProperties"] = False

    return all(_normalize_strict_schema(item) for item in value.values())


def _resolve_output_schema(meta: dict[str, Any]) -> dict[str, Any] | None:
    if not meta.get("structured_output"):
        return None
    raw = meta.get("output_schema")
    if not isinstance(raw, str) or not raw.strip():
        logger.warning("structured output requested without output_schema")
        return None
    class_name = raw.split(".")[-1].strip()
    if not class_name.isidentifier():
        logger.warning("invalid output_schema reference %r", raw)
        return None
    try:
        from thinking_os import cognition_schemas
    except ImportError as exc:
        logger.warning("cognition_schemas import failed: %s", exc)
        return None
    schema_class = getattr(cognition_schemas, class_name, None)
    if schema_class is None or not hasattr(schema_class, "model_json_schema"):
        logger.warning("no Pydantic class %s in cognition_schemas", class_name)
        return None
    try:
        schema = schema_class.model_json_schema()
    except (TypeError, ValueError) as exc:
        logger.warning("model_json_schema() failed for %s: %s", class_name, exc)
        return None
    if not _normalize_strict_schema(schema):
        logger.warning(
            "%s is not compatible with Codex strict output; using JSON-block extraction",
            class_name,
        )
        return None
    return schema
