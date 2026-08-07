"""Coding OS Codex formula dispatcher."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import extract_json_block, load_agent_prompt

logger = logging.getLogger("coding_os.dispatcher.codex_sdk")

_BACKEND_ENV = "COS_CODEX_DISPATCH_BACKEND"
_CLI_BACKEND = "cli"
_PYTHON_SDK_BACKEND = "python-sdk"
_BACKENDS = {_CLI_BACKEND, _PYTHON_SDK_BACKEND}


def _failure_fields(status: str, error: str | None) -> dict[str, Any]:
    if status == "ok":
        return {}
    message = (error or "").lower()
    if status == "timeout":
        return {"error_category": "timeout", "retryable": True, "outcome": "unknown"}
    retry_after: int | None = None
    match = re.search(r"(?:retry after|try again in)\s+(\d+)\s*(?:seconds?|s)?", message)
    if match:
        retry_after = int(match.group(1))
    if any(
        token in message
        for token in ("rate limit", "usage limit", "quota", "too many requests", "429", "capacity")
    ):
        return {
            "error_category": "capacity",
            "retryable": True,
            "retry_after_s": retry_after,
            "outcome": "known_failed",
        }
    if any(
        token in message
        for token in ("unauthorized", "authentication", "not logged in", "401", "403")
    ):
        return {"error_category": "auth", "outcome": "known_failed"}
    # Provider-side overload (529) and internal errors (5xx) are NOT your quota,
    # so they must not open the capacity breaker — but they are the most
    # retryable class there is, and reporting them non-retryable is wrong.
    if any(token in message for token in ("overloaded", "529", "api_error", "500", "502", "503")):
        return {"error_category": "provider", "retryable": True, "outcome": "unknown"}
    if any(token in message for token in ("not in path", "not importable", "unsupported")):
        return {"error_category": "unavailable", "outcome": "known_failed"}
    if any(token in message for token in ("must be absolute", "cannot enforce", "invalid")):
        return {"error_category": "invalid", "outcome": "known_failed"}
    return {"error_category": "provider", "outcome": "unknown"}


def _codex_binary() -> str | None:
    return shutil.which("codex")


def _python_sdk_available() -> bool:
    try:
        import openai_codex  # noqa: F401
    except ImportError:
        return False
    return True


def _dispatch_context(request: DispatchRequest) -> str:
    return (
        "## Dispatch Context\n"
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


def _event_error(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("message") or value)
    return str(value or "Codex turn failed")


def _parse_cli_output(stdout: str) -> tuple[str, str | None]:
    final_response = ""
    failure: str | None = None
    event_count = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            continue
        event_count += 1
        event_type = event["type"]
        if event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                final_response = str(item.get("text") or "")
            elif isinstance(item, dict) and item.get("type") == "error":
                logger.warning("codex item error: %s", _event_error(item.get("message")))
        elif event_type == "turn.failed":
            failure = _event_error(event.get("error"))
        elif event_type == "error":
            failure = _event_error(event.get("message"))
    if event_count == 0:
        final_response = stdout
    return final_response, failure


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


class CodexSDKDispatcher:
    name = "codex-sdk"

    def __init__(self) -> None:
        self._binary = _codex_binary()
        self._sdk_available = _python_sdk_available()
        self._backend = os.environ.get(_BACKEND_ENV, _CLI_BACKEND).strip().lower()

    def available(self) -> bool:
        if self._backend == _CLI_BACKEND:
            return self._binary is not None
        if self._backend == _PYTHON_SDK_BACKEND:
            return self._sdk_available
        return self._binary is not None or self._sdk_available

    def _result(
        self,
        request: DispatchRequest,
        started_at: float,
        *,
        status: str,
        error: str | None = None,
        output_json: dict[str, Any] | None = None,
        raw_transcript: str | None = None,
    ) -> DispatchResult:
        return DispatchResult(
            formula_id=request.formula_id,
            status=status,
            error=error,
            output_json=output_json or {},
            raw_transcript=raw_transcript,
            dispatcher_name=self.name,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            **_failure_fields(status, error),
        )

    def _completed(
        self,
        request: DispatchRequest,
        started_at: float,
        final_response: str,
        raw_transcript: str,
    ) -> DispatchResult:
        output_json = extract_json_block(final_response)
        if not output_json:
            return self._result(
                request,
                started_at,
                status="error",
                error="codex returned no usable EvidenceBundle JSON",
                raw_transcript=raw_transcript,
            )
        return self._result(
            request,
            started_at,
            status="ok",
            output_json=output_json,
            raw_transcript=raw_transcript,
        )

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        started_at = time.monotonic()
        if self._backend not in _BACKENDS:
            return self._result(
                request,
                started_at,
                status="error",
                error=f"unsupported {_BACKEND_ENV}={self._backend!r}",
            )
        if self._backend == _CLI_BACKEND and self._binary is None:
            return self._result(
                request,
                started_at,
                status="error",
                error="codex binary not in PATH",
            )
        if request.max_budget_usd is not None:
            return self._result(
                request,
                started_at,
                status="error",
                error=(
                    "Codex cannot enforce DispatchRequest.max_budget_usd; dispatch was not started"
                ),
            )
        if request.allowed_tools:
            logger.warning(
                "codex does not expose a per-turn allowed_tools API; enforcing read-only sandbox"
            )
        if request.long_context:
            logger.warning(
                "codex does not expose a per-turn long_context switch; using the selected model"
            )
        if request.max_turns not in (None, 1):
            logger.warning(
                "codex runs one thread turn per formula and cannot enforce max_turns=%s",
                request.max_turns,
            )

        try:
            system_body, agent_meta = load_agent_prompt(request.agent_file)
        except FileNotFoundError as exc:
            return self._result(request, started_at, status="error", error=str(exc))
        output_schema = _resolve_output_schema(agent_meta)

        if self._backend == _PYTHON_SDK_BACKEND:
            return await self._dispatch_python_sdk(
                request,
                system_body,
                output_schema,
                started_at,
            )
        return await self._dispatch_cli(request, system_body, output_schema, started_at)

    async def _dispatch_cli(
        self,
        request: DispatchRequest,
        system_body: str,
        output_schema: dict[str, Any] | None,
        started_at: float,
    ) -> DispatchResult:
        assert self._binary is not None
        timeout = max(0.1, float(request.timeout_s))
        with tempfile.TemporaryDirectory(prefix="coding-os-codex-") as temp_dir:
            cmd = [
                self._binary,
                "--ask-for-approval",
                "never",
                "exec",
                "--ignore-user-config",
                "--disable",
                "hooks",
                "--config",
                "mcp_servers={}",
                "--json",
                "--ephemeral",
                "--sandbox",
                "read-only",
            ]
            if request.model:
                cmd.extend(["--model", request.model])
            if output_schema is not None:
                schema_path = Path(temp_dir) / "output-schema.json"
                schema_path.write_text(json.dumps(output_schema), encoding="utf-8")
                cmd.extend(["--output-schema", str(schema_path)])
            cmd.append("-")
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    input=_cli_prompt(system_body, request),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=request.cwd or os.getcwd(),
                )
            except subprocess.TimeoutExpired:
                return self._result(
                    request,
                    started_at,
                    status="timeout",
                    error=f"codex timed out after {timeout}s",
                )
            except FileNotFoundError:
                self._binary = None
                return self._result(
                    request,
                    started_at,
                    status="error",
                    error="codex binary not found at dispatch time",
                )
            except OSError as exc:
                return self._result(
                    request,
                    started_at,
                    status="error",
                    error=f"codex subprocess error: {exc}",
                )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        final_response, failure = _parse_cli_output(stdout)
        if result.returncode != 0:
            logger.warning(
                "codex exited %d for formula=%s: %s",
                result.returncode,
                request.formula_id,
                stderr[:200],
            )
            return self._result(
                request,
                started_at,
                status="error",
                error=failure or f"codex rc={result.returncode}: {stderr[:1000]}",
                raw_transcript=stdout,
            )

        if failure:
            return self._result(
                request,
                started_at,
                status="error",
                error=failure,
                raw_transcript=stdout,
            )
        return self._completed(request, started_at, final_response, stdout)

    async def _dispatch_python_sdk(
        self,
        request: DispatchRequest,
        system_body: str,
        output_schema: dict[str, Any] | None,
        started_at: float,
    ) -> DispatchResult:
        try:
            from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox
        except ImportError:
            return self._result(
                request,
                started_at,
                status="error",
                error=(
                    "openai-codex is not installed; run "
                    "`uv sync --extra codex-sdk` or select the cli backend"
                ),
            )

        timeout = max(0.1, float(request.timeout_s))

        async def run_turn() -> Any:
            config = CodexConfig(
                config_overrides=("features.hooks=false", "mcp_servers={}"),
            )
            async with AsyncCodex(config) as client:
                thread = await client.thread_start(
                    approval_mode=ApprovalMode.deny_all,
                    cwd=request.cwd or os.getcwd(),
                    developer_instructions=system_body,
                    ephemeral=True,
                    model=request.model,
                    sandbox=Sandbox.read_only,
                )
                return await thread.run(
                    _dispatch_context(request),
                    output_schema=output_schema,
                )

        try:
            turn = await asyncio.wait_for(run_turn(), timeout=timeout)
        except asyncio.TimeoutError:
            return self._result(
                request,
                started_at,
                status="timeout",
                error=f"openai-codex timed out after {timeout}s",
            )
        except Exception as exc:
            return self._result(
                request,
                started_at,
                status="error",
                error=f"openai-codex error: {exc}",
            )

        transcript = json.dumps(
            {
                "status": _jsonable(getattr(turn, "status", None)),
                "error": _jsonable(getattr(turn, "error", None)),
                "items": _jsonable(getattr(turn, "items", [])),
                "usage": _jsonable(getattr(turn, "usage", None)),
            },
            ensure_ascii=False,
        )
        turn_error = getattr(turn, "error", None)
        if turn_error:
            return self._result(
                request,
                started_at,
                status="error",
                error=_event_error(_jsonable(turn_error)),
                raw_transcript=transcript,
            )
        return self._completed(
            request,
            started_at,
            str(getattr(turn, "final_response", "") or ""),
            transcript,
        )


def build_dispatcher() -> CodexSDKDispatcher:
    return CodexSDKDispatcher()
