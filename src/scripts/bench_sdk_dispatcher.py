"""
Real-world benchmark for the claude-sdk dispatcher.

Spawns 3 formula-agents (F2/F5/F7) across 2 scenarios and records:
  - latency_ms (wall clock)
  - status (ok/timeout/error)
  - output_json non-empty
  - token cost if provided by ResultMessage

Run: uv run --extra claude-sdk python scripts/bench_sdk_dispatcher.py

NOTE: This calls the real Claude Code CLI — requires claude to be installed
and authenticated on the local machine.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "core" / "thinking_os"))

from dispatcher import DispatchRequest

# Load the claude-sdk dispatcher by path (core/ can't import it directly)
spec = importlib.util.spec_from_file_location(
    "claude_sdk_dispatcher",
    ROOT / "adapters" / "claude" / "sdk_dispatcher.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


SCENARIOS = [
    {
        "name": "F2-decompose-small",
        "formula": "analyst",
        "agent_file": str(ROOT / "src/core/thinking_os/agents/analyst.md"),
        "prompt": (
            "Decompose this task: 'Add a health-check endpoint /healthz to "
            "a FastAPI service that returns {status: ok, version: X}.' "
            "Keep scope trivial. Emit a small JSON slice."
        ),
        "input_slice": {"task_description": "add /healthz endpoint"},
        "timeout_s": 90,
    },
    {
        "name": "F7-debug-syntax",
        "formula": "debugger",
        "agent_file": str(ROOT / "src/core/thinking_os/agents/debugger.md"),
        "prompt": (
            "Debug this Python error: "
            "`TypeError: '<' not supported between instances of str and int` "
            "raised in `sorted(items, key=lambda x: x['priority'])` where some "
            "items have int priority and others have string. "
            "Emit the 5-phase debug JSON."
        ),
        "input_slice": {"task_description": "fix sort TypeError"},
        "timeout_s": 90,
    },
    {
        "name": "F5-implement-trivial",
        "formula": "implementer",
        "agent_file": str(ROOT / "src/core/thinking_os/agents/implementer.md"),
        "prompt": (
            "Implement plan: add a Python function `slugify(s: str) -> str` "
            "that lowercases, strips, and replaces spaces with '-'. "
            "Do not actually write files; just emit the implementation JSON slice."
        ),
        "input_slice": {"task_description": "add slugify helper"},
        "timeout_s": 90,
    },
]


async def run_one(d, scenario) -> dict:
    req = DispatchRequest(
        formula_id=scenario["formula"],
        agent_file=scenario["agent_file"],
        prompt=scenario["prompt"],
        input_slice=scenario["input_slice"],
        intensity="light",
        timeout_s=scenario["timeout_s"],
    )
    t0 = time.monotonic()
    result = await d.dispatch(req)
    wall_ms = int((time.monotonic() - t0) * 1000)
    return {
        "scenario": scenario["name"],
        "formula": scenario["formula"],
        "status": result.status,
        "latency_ms": result.latency_ms,
        "wall_ms": wall_ms,
        "output_keys": sorted(result.output_json.keys())[:6],
        "output_size": len(json.dumps(result.output_json)),
        "error": result.error,
        "transcript_chars": len(result.raw_transcript or ""),
    }


async def main():
    d = mod.ClaudeSDKDispatcher()
    if not d.available():
        print("claude-agent-sdk not available; aborting")
        return 1

    print(f"\n=== Benchmark: claude-sdk dispatcher × {len(SCENARIOS)} scenarios ===\n")
    results = []
    for sc in SCENARIOS:
        print(f"→ running {sc['name']} ...")
        try:
            r = await run_one(d, sc)
        except Exception as exc:
            r = {
                "scenario": sc["name"],
                "formula": sc["formula"],
                "status": "crashed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(r)
        print(
            f"  status={r.get('status')} latency={r.get('latency_ms')}ms "
            f"output_keys={r.get('output_keys')}"
        )

    print("\n=== Sequential summary ===")
    ok = sum(1 for r in results if r["status"] == "ok")
    total_ms = sum(r.get("latency_ms", 0) for r in results)
    print(f"ok: {ok}/{len(results)}   total_latency: {total_ms}ms")

    # ---- Parallel scenario: F7 + F5 concurrently ----
    print("\n=== Parallel scenario: F7+F5 via asyncio.gather ===")
    t0 = time.monotonic()
    par_results = await asyncio.gather(
        run_one(d, SCENARIOS[1]),  # F7
        run_one(d, SCENARIOS[2]),  # F5
        return_exceptions=True,
    )
    par_wall_ms = int((time.monotonic() - t0) * 1000)
    par_ok = sum(1 for r in par_results if isinstance(r, dict) and r.get("status") == "ok")
    seq_equivalent = results[1].get("latency_ms", 0) + results[2].get("latency_ms", 0)
    print(
        f"parallel wall: {par_wall_ms}ms   "
        f"vs sequential equivalent: {seq_equivalent}ms   "
        f"speedup: {seq_equivalent / par_wall_ms:.2f}x"
    )

    print("\n=== Full results ===")
    print(
        json.dumps(
            {
                "sequential": results,
                "parallel": par_results,
                "parallel_wall_ms": par_wall_ms,
                "sequential_equivalent_ms": seq_equivalent,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if ok == len(results) and par_ok == 2 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
