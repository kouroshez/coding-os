"""Shared harness for the cos_* MCP audit — server bootstrap, call helpers, fixtures.

Imported by audit_mcp_tools.py and its per-group probe modules. Lives in its own
module so the probes never import the entry script back (running it as __main__
would otherwise load the server twice under two module names).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "core"))
sys.path.insert(0, str(ROOT / "src" / "core" / "thinking_os"))

os.environ.setdefault("COS_DB_PATH", str(ROOT / ".coding-os/coding-os.db"))

print("Loading server…")
import thinking_os.server as srv_mod

MCP = srv_mod.mcp
print("Done.\n")

# ── helpers ──────────────────────────────────────────────────────────────────

Results: list[tuple[str, str, str]] = []


async def _call(tool: str, **kwargs) -> dict:
    """Call tool via FastMCP. call_tool returns (list[TextContent], meta_dict)."""
    try:
        result_list, _meta = await MCP.call_tool(tool, kwargs)
        if result_list:
            text = getattr(result_list[0], "text", None) or str(result_list[0])
        else:
            return {"ok": False, "_exc": "empty result list"}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"ok": False, "_raw": text[:400]}
    except Exception as exc:
        return {"ok": False, "_exc": f"{type(exc).__name__}: {exc}"}


def _rec(group: str, name: str, env: dict, *, ms: float = 0.0) -> dict:
    ok = env.get("ok")
    if ok is True:
        status, detail = "PASS", f"{ms:.0f}ms"
    elif ok is False:
        err = env.get("error") or {}
        cat = err.get("category") or env.get("_exc", "?")
        msg = (err.get("message") or env.get("_raw") or env.get("_exc", ""))[:160]
        status, detail = "FAIL", f"cat={cat} | {msg}"
    else:
        status, detail = "WARN", f"missing 'ok': {str(env)[:100]}"
    sym = "✓" if status == "PASS" else ("⚠" if status == "WARN" else "✗")
    print(f"  {sym} {name}: {detail}")
    Results.append((group, name, f"{status}: {detail}"))
    return env


def _ok(group: str, label: str, cond: bool, note: str) -> None:
    sym = "✓" if cond else "✗"
    print(f"    {sym} [{note}]")
    Results.append((group, f"  {label}", f"{'PASS' if cond else 'FAIL'}: {note}"))


def _d(env: dict) -> dict:
    return env.get("data") or {}


async def T(tool: str, **kwargs) -> dict:
    t0 = time.perf_counter()
    env = await _call(tool, **kwargs)
    return env, (time.perf_counter() - t0) * 1000


# ── fixtures ──────────────────────────────────────────────────────────────────

from thinking_os.database import init_db

_DB_PATH = Path(os.environ.get("COS_DB_PATH") or ROOT / ".coding-os/coding-os.db")
if not _DB_PATH.exists():
    sys.exit(f"audit_mcp_tools: DB not found at {_DB_PATH} — run `cos init` / `make` first.")
DB = init_db(str(_DB_PATH))
_obs = DB.execute("SELECT id FROM observations LIMIT 1").fetchone()
OBS_ID = _obs["id"] if _obs else 1
_pat = DB.execute("SELECT id FROM learned_patterns LIMIT 1").fetchone()
PAT_ID = _pat["id"] if _pat else 1
_task = DB.execute("SELECT task_id FROM tasks LIMIT 1").fetchone()
TASK_ID = _task["task_id"] if _task else "TASK-001"
SESSION = "ses-claude-audit-smoke"

GRAPH_FILE = "src/core/graph_os/tools/graph.py"
GRAPH_UID = f"code:file:{GRAPH_FILE}"
FUNC_UID = "code:function:src/core/graph_os/tools/graph.py::_resolve_uid"
