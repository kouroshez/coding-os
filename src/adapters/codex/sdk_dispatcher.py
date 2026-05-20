"""Coding OS — Codex dispatcher (adapters/codex)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time

from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import extract_json_block, load_agent_prompt

logger = logging.getLogger("coding_os.dispatcher.codex_sdk")


def _codex_binary() -> str | None:
    """Return the absolute path of the `codex` binary, or None."""
    return shutil.which("codex")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class CodexSDKDispatcher:
    name = "codex-sdk"
    # Codex CLI flag for non-interactive JSON-output mode.
    # If the installed version does not support this flag the first dispatch
    # detects the error and flips `_available` to False so subsequent calls
    # fall through to the default dispatcher immediately.
    _CODEX_JSON_FLAG = "--json"

    def __init__(self) -> None:
        self._binary = _codex_binary()
        self._available = self._binary is not None

    def available(self) -> bool:
        return self._available

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        t0 = time.monotonic()
        if not self._available or self._binary is None:
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error="codex binary not in PATH",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        # Build the prompt. Codex reads a single system prompt from --instructions
        # and the user message from stdin (or --prompt flag depending on version).
        try:
            system_body, _meta = load_agent_prompt(request.agent_file)
        except FileNotFoundError as exc:
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=str(exc),
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        # Parity with claude/sdk_dispatcher.py: always include system body +
        # dispatch context + structured input slice + task prompt + output
        # instruction.  The old `prompt or system_body` was either/or — it
        # silently dropped the formula body whenever a task prompt was provided.
        user_message = (
            f"{system_body}\n\n"
            f"## Dispatch Context\n"
            f"- Formula: {request.formula_id}\n"
            f"- Persona: {request.persona_id or 'n/a'}\n"
            f"- Intensity: {request.intensity}\n\n"
            f"## Input Context (upstream formulas only)\n"
            f"```json\n{json.dumps(request.input_slice, indent=2)}\n```\n\n"
            f"## Task\n"
            f"{request.prompt}\n\n"
            f"Produce the EvidenceBundle slice for this formula as a single "
            f"```json ... ``` block at the end of your response."
        )

        cmd = [self._binary, "--no-interactive", self._CODEX_JSON_FLAG, user_message]
        cwd = request.cwd or os.getcwd()
        timeout = max(10.0, float(request.timeout_s))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                formula_id=request.formula_id,
                status="timeout",
                error=f"codex timed out after {timeout}s",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except FileNotFoundError:
            # Binary vanished between available() check and actual call.
            self._available = False
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error="codex binary not found at dispatch time",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except OSError as exc:
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"codex subprocess error: {exc}",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode != 0:
            # Detect unsupported flags (old CLI version) and disable JSON mode.
            if "--no-interactive" in stderr or "unknown flag" in stderr.lower():
                self._available = False
            logger.warning(
                "codex exited %d for formula=%s: %s",
                result.returncode,
                request.formula_id,
                stderr[:200],
            )
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"codex rc={result.returncode}: {stderr[:300]}",
                output_json=extract_json_block(stdout),
                raw_transcript=stdout,
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        output_json = extract_json_block(stdout)
        return DispatchResult(
            formula_id=request.formula_id,
            status="ok",
            output_json=output_json,
            raw_transcript=stdout,
            dispatcher_name=self.name,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


def build_dispatcher() -> CodexSDKDispatcher:
    """Factory entry-point — mirrors adapters/claude/sdk_dispatcher.py."""
    return CodexSDKDispatcher()
