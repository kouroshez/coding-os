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

from adapters.codex._codex_pricing import cost_usd
from adapters.codex._codex_prompt import (
    _cli_prompt as _cli_prompt,
    _dispatch_context as _dispatch_context,
    _jsonable as _jsonable,
    _normalize_strict_schema as _normalize_strict_schema,
    _resolve_output_schema as _resolve_output_schema,
)
from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import (
    extract_json_block,
    load_agent_prompt,
)

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


def _event_error(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("message") or value)
    return str(value or "Codex turn failed")


def _parse_cli_output(stdout: str) -> tuple[str, str | None, dict | None]:
    final_response = ""
    failure: str | None = None
    usage: dict | None = None
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
        elif event_type == "turn.completed":
            # Codex reports token counts but no USD figure; recording the tokens
            # is what makes "how much did Codex get used" answerable at all.
            reported = event.get("usage")
            if isinstance(reported, dict):
                usage = reported
        elif event_type == "turn.failed":
            failure = _event_error(event.get("error"))
        elif event_type == "error":
            failure = _event_error(event.get("message"))
    if event_count == 0:
        final_response = stdout
    return final_response, failure, usage


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
        usage: dict | None = None,
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
        if usage:
            # Stamped by the adapter because only the runtime knows its own
            # accounting; core merges identity into the same _meta afterwards and
            # persistence writes it to usage_jsonb. The CLI reports no USD figure,
            # so the cost is priced from the descriptor's published table — and
            # stays absent when no table covers the model rather than reading 0.
            output_json.setdefault("_meta", {})
            if isinstance(output_json["_meta"], dict):
                output_json["_meta"]["usage"] = usage
                priced = cost_usd(usage, request.model)
                if priced is not None:
                    output_json["_meta"]["total_cost_usd"] = priced
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
        final_response, failure, usage = _parse_cli_output(stdout)
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
        return self._completed(request, started_at, final_response, stdout, usage)

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


def requirement() -> dict[str, str]:
    """What is missing for dispatch to run, and how to supply it."""
    if CodexSDKDispatcher().available():
        return {}
    return {
        "missing": "the codex CLI on PATH",
        "remedy": "install the Codex CLI, or set COS_CODEX_BACKEND=python_sdk with the SDK installed",
    }
