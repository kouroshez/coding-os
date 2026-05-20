#!/usr/bin/env python3
"""
Phase C E2E verification — defensive Python orchestration.

Replaces the older bash version which kept hanging on `uv run` heredocs
inside `$(...)` command substitution. Every subprocess call here has an
explicit timeout so the script can NEVER stall the user indefinitely.

What it verifies (in order, fail-fast):
    1. Preconditions (external task corpus path, uv installed)
    2. coding-os init creates a fresh project
    3. External tasks copy in
    4. task_sync first run (N new, 0 errors)
    5. task_sync second run (N skipped, incremental works)
    6. Python query: filter, deps, dependents, semantic, substring safety
    7. MCP server registers all 4 cos_task_* tools (introspection only,
       not stdio JSON-RPC — that's covered by pytest)

Run:
    COS_CORPUS_PATH=/path/to/external-project python3 scripts/verify_phase_c_e2e.py

Requires: the COS_CORPUS_PATH directory must contain `docs/tasks/TASK-*.md`
and a `docs/tasks.md` index. Use any project with a Scrumban-style task corpus.

Exit: 0 on success, non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---- Configuration ---------------------------------------------------------

COS_ROOT = Path(__file__).resolve().parent.parent.parent
_CORPUS_ENV = os.environ.get("COS_CORPUS_PATH")
if not _CORPUS_ENV:
    print(
        "FAIL: COS_CORPUS_PATH environment variable is required.\n"
        "      Set it to a directory containing docs/tasks/TASK-*.md and docs/tasks.md.\n"
        "      Example: COS_CORPUS_PATH=/path/to/your-project python3 scripts/verify_phase_c_e2e.py",
        file=sys.stderr,
    )
    sys.exit(2)
CORPUS_PATH = Path(_CORPUS_ENV).resolve()

# Per-step timeouts (seconds). Generous but bounded — no step is allowed
# to hang indefinitely.
TIMEOUT_INIT = 60
TIMEOUT_SYNC_FIRST = 180   # cold sync includes embedding model load
TIMEOUT_SYNC_SECOND = 30   # incremental sync should be fast
TIMEOUT_QUERY = 120        # includes one-time model load for semantic
TIMEOUT_MCP_INTROSPECT = 60


# ---- Output helpers --------------------------------------------------------

def info(msg: str) -> None:
    print(f"  INFO: {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  OK: {msg}", flush=True)


def fail(msg: str) -> "None":
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def section(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


# ---- Defensive subprocess runner -------------------------------------------

def run(cmd: list[str], *, timeout: int, env: dict[str, str] | None = None,
        cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess with mandatory timeout. Never blocks indefinitely.

    Args:
        cmd: argv list (no shell).
        timeout: hard cap in seconds. The process is killed on expiry.
        env: optional environment overrides.
        cwd: optional working directory.

    Returns:
        CompletedProcess on success.

    Raises SystemExit on timeout or non-zero exit.
    """
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        fail(f"TIMEOUT after {timeout}s: {' '.join(cmd[:3])}...")
    if result.returncode != 0:
        fail(
            f"command failed (rc={result.returncode}): {' '.join(cmd[:5])}\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )
    return result


# ---- Step implementations --------------------------------------------------

def precheck() -> int:
    section(f"Phase C E2E verification — COS_CORPUS_PATH={CORPUS_PATH}")
    if not CORPUS_PATH.exists():
        fail(f"corpus path not found: {CORPUS_PATH}")
    tasks_src = CORPUS_PATH / "docs" / "tasks"
    if not tasks_src.is_dir():
        fail(f"corpus tasks dir not found: {tasks_src}")
    task_count = len(list(tasks_src.glob("TASK-*.md")))
    if task_count < 1:
        fail(f"No TASK-*.md files in {tasks_src}")
    if shutil.which("uv") is None:
        fail("`uv` not on PATH")
    ok(f"external corpus: {task_count} tasks")
    return task_count


def init_project() -> Path:
    section("1. coding-os init")
    project = Path(tempfile.mkdtemp(prefix="cos-phase-c-e2e-"))
    info(f"temp project: {project}")
    run(
        ["uv", "run", "--directory", str(COS_ROOT), "python", "-m", "cli.main",
         "init", "--agent", "claude", "--template", "django", "--template", "nextjs",
         "--project-dir", str(project)],
        timeout=TIMEOUT_INIT,
    )
    ok("init succeeded")
    return project


def copy_tasks(project: Path) -> int:
    section("2. copy external task corpus")
    tasks_dir = project / "docs" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    src = CORPUS_PATH / "docs" / "tasks"
    copied = 0
    for src_file in src.glob("TASK-*.md"):
        shutil.copy2(src_file, tasks_dir / src_file.name)
        copied += 1
    # Copy the index too
    shutil.copy2(CORPUS_PATH / "docs" / "tasks.md", project / "docs" / "tasks.md")
    ok(f"copied {copied} task files + tasks.md")
    return copied


def sync_first_run(project: Path) -> dict:
    section("3. task_sync run 1 (cold)")
    result = run(
        ["uv", "run", "--extra", "rag", "--directory", str(COS_ROOT),
         "python", "-m", "core.thinking_os.task_sync",
         "--project-root", str(project),
         "--db", str(project / ".coding-os" / "coding-os.db")],
        timeout=TIMEOUT_SYNC_FIRST,
    )
    # Parse the JSON line in the output
    stats = _extract_json_stats(result.stdout)
    if stats["errors"] != 0:
        fail(f"task_sync run 1 reported {stats['errors']} errors")
    if stats["new"] < 1:
        fail(f"task_sync run 1 inserted {stats['new']} rows (expected >= 1)")
    ok(f"new={stats['new']}, errors={stats['errors']}")
    return stats


def sync_second_run(project: Path, expected_count: int) -> dict:
    section("4. task_sync run 2 (incremental, expect all skipped)")
    result = run(
        ["uv", "run", "--extra", "rag", "--directory", str(COS_ROOT),
         "python", "-m", "core.thinking_os.task_sync",
         "--project-root", str(project),
         "--db", str(project / ".coding-os" / "coding-os.db")],
        timeout=TIMEOUT_SYNC_SECOND,
    )
    stats = _extract_json_stats(result.stdout)
    if stats["skipped"] != expected_count:
        fail(
            f"task_sync run 2 should skip {expected_count}, got skipped={stats['skipped']}"
        )
    if stats["new"] != 0 or stats["updated"] != 0:
        fail(
            f"task_sync run 2 should be no-op, got new={stats['new']} "
            f"updated={stats['updated']}"
        )
    ok(f"skipped={stats['skipped']} (incremental works)")
    return stats


def python_queries(project: Path) -> None:
    section("5. Python queries (filter, deps, dependents, semantic, substring)")
    # Write the query script to a temp file inside the project — avoids
    # heredoc-inside-command-substitution fragility.
    query_script = project / "_e2e_query.py"
    query_script.write_text(
        'import os, sys\n'
        'sys.path.insert(0, os.environ["COS_ROOT"] + "/core/thinking_os")\n'
        'from database import init_db\n'
        'from tools.tasks import task_by_filter, task_dependencies, task_dependents, task_search\n'
        '\n'
        'conn = init_db(os.environ["TEST_DB"])\n'
        'total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]\n'
        'print(f"TOTAL:{total}")\n'
        '\n'
        'results = task_by_filter(conn, status="open", domain="BACKEND", limit=3)\n'
        'print(f"FILTER_BACKEND_OPEN:{len(results)}")\n'
        '\n'
        'deps = task_dependencies(conn, "TASK-199")\n'
        'print(f"DEPS_TASK199:{len(deps)}")\n'
        'if deps:\n'
        '    print(f"DEPS_TASK199_FIRST:{deps[0][\'task_id\']}")\n'
        '\n'
        'dependents = task_dependents(conn, "TASK-195")\n'
        'print(f"DEPENDENTS_TASK195:{len(dependents)}")\n'
        '\n'
        'fps = task_dependents(conn, "TASK-019")\n'
        'print(f"FALSE_POSITIVES_TASK019:{len(fps)}")\n'
        '\n'
        'semantic = task_search(conn, "payment splitting multi vendor revenue", limit=3)\n'
        'print(f"SEMANTIC_COUNT:{len(semantic)}")\n'
        'if semantic:\n'
        '    top = semantic[0]\n'
        '    print(f"SEMANTIC_TOP:{top[\'task_id\']}|{top[\'title\']}")\n'
        '\n'
        'conn.close()\n',
        encoding="utf-8",
    )

    result = run(
        ["uv", "run", "--extra", "rag", "--directory", str(COS_ROOT),
         "python", str(query_script)],
        timeout=TIMEOUT_QUERY,
        env={
            "COS_ROOT": str(COS_ROOT),
            "TEST_DB": str(project / ".coding-os" / "coding-os.db"),
        },
    )
    metrics = _parse_kv_lines(result.stdout)

    total = int(metrics.get("TOTAL", "0"))
    if total < 1:
        fail(f"Expected tasks indexed, got TOTAL={total}")
    ok(f"total tasks: {total}")

    backend_open = int(metrics.get("FILTER_BACKEND_OPEN", "0"))
    if backend_open < 1:
        fail(f"task_by_filter(BACKEND,open) returned 0 results")
    ok(f"task_by_filter(BACKEND,open): {backend_open}")

    deps_count = int(metrics.get("DEPS_TASK199", "0"))
    deps_first = metrics.get("DEPS_TASK199_FIRST", "")
    if deps_count != 1 or deps_first != "TASK-195":
        fail(
            f"TASK-199 should depend on exactly TASK-195, "
            f"got count={deps_count} first={deps_first!r}"
        )
    ok("task_dependencies(TASK-199) → TASK-195")

    dependents = int(metrics.get("DEPENDENTS_TASK195", "0"))
    if dependents < 5:
        fail(f"TASK-195 should have ≥5 dependents, got {dependents}")
    ok(f"task_dependents(TASK-195): {dependents} downstream tasks")

    fps = int(metrics.get("FALSE_POSITIVES_TASK019", "999"))
    if fps != 0:
        fail(
            f"SUBSTRING SAFETY FAILURE: task_dependents(TASK-019) "
            f"returned {fps} (expected 0)"
        )
    ok("substring safety: TASK-019 doesn't match TASK-195/196/199")

    sem = int(metrics.get("SEMANTIC_COUNT", "0"))
    if sem < 1:
        fail("semantic task_search returned 0 results")
    sem_top = metrics.get("SEMANTIC_TOP", "")
    ok(f"semantic search: top={sem_top}")


def mcp_introspect() -> None:
    section("6. MCP tool registration (module introspection)")
    # Use a temp script (no heredoc, no command substitution chains)
    introspect_script = COS_ROOT / "src" / "scripts" / "_mcp_introspect.py"
    # Avoid nested quotes inside f-strings (Python 3.10 doesn't support
    # them) by computing the missing-string outside the f-string.
    introspect_script.write_text(
        'import asyncio, os, sys\n'
        'sys.path.insert(0, os.environ["COS_ROOT"] + "/core/thinking_os")\n'
        'import server\n'
        'tools = asyncio.run(server.mcp.list_tools())\n'
        'names = [t.name for t in tools]\n'
        'expected = ["cos_task_search", "cos_task_dependencies", "cos_task_dependents", "cos_task_by_filter"]\n'
        'missing = [e for e in expected if e not in names]\n'
        'missing_str = ",".join(missing) if missing else "NONE"\n'
        'print("TOOLS_TOTAL:" + str(len(names)))\n'
        'print("MISSING:" + missing_str)\n',
        encoding="utf-8",
    )
    try:
        result = run(
            ["uv", "run", "--extra", "rag", "--directory", str(COS_ROOT),
             "python", str(introspect_script)],
            timeout=TIMEOUT_MCP_INTROSPECT,
            env={"COS_ROOT": str(COS_ROOT)},
        )
    finally:
        if introspect_script.exists():
            introspect_script.unlink()

    metrics = _parse_kv_lines(result.stdout)
    total = int(metrics.get("TOOLS_TOTAL", "0"))
    missing = metrics.get("MISSING", "")
    if missing != "NONE":
        fail(f"MCP tools missing: {missing}")
    if total < 17:
        fail(f"Expected ≥17 MCP tools, got {total}")
    ok(f"MCP server registers {total} tools (all 4 cos_task_* present)")


# ---- Output parsing helpers ------------------------------------------------

def _extract_json_stats(stdout: str) -> dict:
    """Find and parse the JSON object from task_sync stdout."""
    # task_sync prints {"status": "ok", "stats": {...}}
    start = stdout.find("{")
    if start < 0:
        fail(f"could not find JSON in stdout:\n{stdout[:500]}")
    try:
        parsed = json.loads(stdout[start:])
    except json.JSONDecodeError as exc:
        fail(f"could not parse JSON: {exc}\nstdout: {stdout[:500]}")
    return parsed.get("stats", {})


def _parse_kv_lines(stdout: str) -> dict[str, str]:
    """Parse `KEY:VALUE` lines into a dict.

    Accepts any line whose left side is an UPPERCASE token (with optional
    underscores or digits). Skips warnings and progress lines so the
    output of `uv` / model loaders doesn't pollute the dict.
    """
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        if line.startswith(("Warning", "Loading", "warning", "[1m")):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        # UPPERCASE-only keys (digits / underscores allowed)
        if key and all(c.isupper() or c.isdigit() or c == "_" for c in key):
            out[key] = value.strip()
    return out


# ---- Main ------------------------------------------------------------------

def main() -> None:
    nako_count = precheck()
    project = init_project()
    try:
        copied = copy_tasks(project)
        first = sync_first_run(project)
        sync_second_run(project, expected_count=first["new"] + first["updated"])
        python_queries(project)
        mcp_introspect()
    finally:
        info(f"temp project preserved at {project}")

    print("\n==========================================")
    print("ALL CHECKS PASSED")
    print("==========================================")
    sys.exit(0)


if __name__ == "__main__":
    main()
