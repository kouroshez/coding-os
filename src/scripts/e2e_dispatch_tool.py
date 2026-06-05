"""
End-to-end test for cos_dispatch_formula_run and cos_dispatch_parallel_run.

Verifies the full path:
  MCP tool call → dispatcher factory → claude-agent-sdk → real Claude Code →
  ```json``` block → EvidenceBundle persistence → formula_dispatches row.

Run: uv run --extra claude-sdk python scripts/e2e_dispatch_tool.py

NOTE: Spawns real Claude Code sub-sessions. Expect ~30-60s total.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src" / "core" / "thinking_os"))

# Isolate E2E state under a sandbox dir so we don't pollute real session files
SANDBOX = ROOT / ".coding-os" / "e2e-sdk-test"
SANDBOX.mkdir(parents=True, exist_ok=True)
os.environ["COS_AGENT"] = "claude"
os.environ["COS_AGENT_DIR"] = str(SANDBOX)

# Redirect evidence bundle to sandbox
SESSION_ID = f"ses-claude-e2e-{int(time.time())}"
TASK_MARKER = "e2e-dispatch-sdk-test"
PERSONA_ID = "senior-backend"

# Import after env setup
from tools.cognition import (
    _load_bundle,
    register_cos_dispatch_formula_run,
    register_cos_dispatch_parallel_run,
)


class FakeMCP:
    """Minimal fake matching the @mcp.tool(name=…) decorator shape."""

    def __init__(self):
        self.tools = {}

    def tool(self, name, description="", **kw):
        def deco(fn):
            self.tools[name] = fn
            return fn

        return deco


def run_single(mcp, db_path) -> dict:
    print("\n=== Single-formula dispatch (F7 — debug) ===")
    fn = mcp.tools["cos_dispatch_formula_run"]
    t0 = time.monotonic()
    raw = fn(
        formula_id="debugger",
        session_id=SESSION_ID,
        task_marker=TASK_MARKER,
        persona_id=PERSONA_ID,
        intensity="light",
        timeout_s=90.0,
    )
    wall_ms = int((time.monotonic() - t0) * 1000)
    envelope = json.loads(raw) if isinstance(raw, str) else raw
    print(f"  envelope.ok: {envelope.get('ok')}")
    data = envelope.get("data", {})
    print(f"  status: {data.get('status')}")
    print(f"  dispatcher: {data.get('dispatcher_name')}")
    print(f"  latency_ms: {data.get('latency_ms')}")
    print(f"  output keys: {sorted(list(data.get('output_json', {}).keys()))[:6]}")
    print(f"  bundle_fields_filled: {data.get('bundle_fields_filled')}")
    print(f"  wall_ms: {wall_ms}")
    return {"envelope": envelope, "wall_ms": wall_ms}


def run_parallel(mcp, db_path) -> dict:
    print("\n=== Parallel dispatch (F5+F7 concurrent) ===")
    fn = mcp.tools["cos_dispatch_parallel_run"]
    t0 = time.monotonic()
    raw = fn(
        formula_ids=["implementer", "debugger"],
        session_id=SESSION_ID,
        task_marker=TASK_MARKER + "-par",
        persona_id=PERSONA_ID,
        intensity="light",
        timeout_s=90.0,
    )
    wall_ms = int((time.monotonic() - t0) * 1000)
    envelope = json.loads(raw) if isinstance(raw, str) else raw
    data = envelope.get("data", {})
    print(f"  envelope.ok: {envelope.get('ok')}")
    print(f"  ok_count: {data.get('ok_count')}/{data.get('total')}")
    print(f"  parallel_wall_ms: {data.get('parallel_wall_ms')}")
    print(f"  total wall_ms (inc. serialization): {wall_ms}")
    for r in data.get("results", []):
        print(
            f"    → {r['formula_id']}: status={r['status']} "
            f"latency={r['latency_ms']}ms fields_filled={r['bundle_fields_filled']}"
        )
    return {"envelope": envelope, "wall_ms": wall_ms}


def verify_bundle():
    print("\n=== Bundle persistence check ===")
    bundle = _load_bundle(SESSION_ID, TASK_MARKER, PERSONA_ID)
    filled = []
    for attr in (
        "researcher",
        "analyst",
        "architect",
        "documenter",
        "implementer",
        "reviewer",
        "debugger",
        "security_auditor",
        "deployer",
        "observer",
        "refactorer",
    ):
        if getattr(bundle, attr, None) is not None:
            filled.append(attr)
    print(f"  populated fields: {filled}")
    return filled


def verify_db_row(db_path):
    print("\n=== DB audit row check (formula_dispatches) ===")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT formula_id, status, latency_ms "
            "FROM formula_dispatches WHERE session_id=? ORDER BY rowid DESC LIMIT 10",
            (SESSION_ID,),
        ).fetchall()
    for r in rows:
        print(f"  {r}")
    return rows


def main():
    from database import DEFAULT_DB_PATH

    db_path = str(DEFAULT_DB_PATH)

    mcp = FakeMCP()
    register_cos_dispatch_formula_run(mcp, db_path)
    register_cos_dispatch_parallel_run(mcp, db_path)
    print(f"registered tools: {list(mcp.tools.keys())}")

    single = run_single(mcp, db_path)
    parallel = run_parallel(mcp, db_path)
    filled = verify_bundle()
    rows = verify_db_row(db_path)

    print("\n=== E2E Summary ===", file=sys.stderr)
    single_ok = (
        single["envelope"].get("ok") is True and single["envelope"]["data"].get("status") == "ok"
    )
    parallel_ok = (
        parallel["envelope"].get("ok") is True
        and parallel["envelope"]["data"].get("ok_count", 0) >= 1
    )
    bundle_ok = "debugger" in filled and "implementer" in filled
    db_ok = len(rows) >= 2
    print(f"  single dispatch:    {'✓' if single_ok else '✗'}", file=sys.stderr)
    print(f"  parallel dispatch:  {'✓' if parallel_ok else '✗'}", file=sys.stderr)
    print(f"  bundle persisted:   {'✓' if bundle_ok else '✗'} ({filled})", file=sys.stderr)
    print(f"  DB audit row:       {'✓' if db_ok else '✗'} ({len(rows)} rows)", file=sys.stderr)
    ok = single_ok and parallel_ok and bundle_ok and db_ok
    print(f"\nE2E: {'PASS' if ok else 'FAIL'}", file=sys.stderr)
    # Machine-readable verdict on stdout (the result a caller scrapes).
    print(
        json.dumps(
            {
                "result": "pass" if ok else "fail",
                "single_ok": single_ok,
                "parallel_ok": parallel_ok,
                "bundle_ok": bundle_ok,
                "db_ok": db_ok,
                "populated_fields": filled,
                "db_rows": len(rows),
            }
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
