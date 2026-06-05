"""Real one-shot dispatch smoke test for hardened ClaudeSDKDispatcher.

exclude_dynamic_sections, setting_sources=['project'],
permission_mode='dontAsk', mcp__coding-os__* allow-list, role skills
inheritance) actually flies through claude-agent-sdk 0.1.73 against the
real Claude CLI. Source-of-truth doc: docs/adapters/claude-sdk.md §13.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _load_dispatcher():
    spec = importlib.util.spec_from_file_location(
        "sdkd", REPO / "src" / "adapters" / "claude" / "sdk_dispatcher.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_dispatcher()


async def main() -> int:
    sys.path.insert(0, str(REPO / "src" / "core"))
    from thinking_os.dispatcher import DispatchRequest

    dispatcher = _load_dispatcher()
    if not dispatcher.available():
        print("SKIP: claude-agent-sdk not importable")
        return 0

    agent_file = REPO / "src" / "core" / "thinking_os" / "agents" / "debugger.md"
    if not agent_file.exists():
        print(f"FAIL: agent file missing: {agent_file}")
        return 1

    request = DispatchRequest(
        formula_id="debugger",
        agent_file=str(agent_file),
        prompt=(
            "Debug this trivial bug: a Python `sorted([1, 'a'])` raises "
            "`TypeError: '<' not supported between instances of 'str' and 'int'`. "
            "Identify root cause and propose a one-line fix."
        ),
        input_slice={
            "task": {"id": "smoke-test", "title": "TypeError smoke"},
            "evidence": {"researcher": {}, "analyst": {}},
        },
        intensity="light",
        timeout_s=120.0,
        cwd=str(REPO),
    )

    print("→ dispatching debugger (light) …")
    result = await dispatcher.dispatch(request)

    print(f"  status:          {result.status}")
    print(f"  dispatcher_name: {result.dispatcher_name}")
    print(f"  latency_ms:      {result.latency_ms}")
    if result.error:
        print(f"  error:           {result.error}")
    if result.output_json:
        keys = sorted(result.output_json.keys())
        print(f"  output_json keys: {keys}")

    if result.status == "ok" and result.output_json:
        print("\nSMOKE: PASS")
        return 0
    print(f"\nSMOKE: FAIL ({result.status})")
    if result.raw_transcript:
        print("--- transcript head ---")
        print(result.raw_transcript[:1500])
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
