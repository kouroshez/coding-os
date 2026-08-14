#!/usr/bin/env python3
"""
Thinking OS — Health Check Suite.

Checks database health, hook integrity, gate state, and learning pipeline status.
Outputs both human-readable summary and JSON for programmatic consumption.

Usage:
    python3 src/core/thinking_os/health_check.py          # human-readable
    python3 src/core/thinking_os/health_check.py --json    # JSON output
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _health_report import print_human_readable as print_human_readable
from database import DEFAULT_DB_PATH, get_connection, get_db_stats, get_schema_version, has_fts5

# ── Constants ────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Hooks live in src/core/ (the SSOT). Adapter install scripts symlink them
# into .claude/hooks/ or .codex/hooks/ — but health checks read from source.
HOOKS_DIR = PROJECT_ROOT / "src" / "core" / "hooks"

# Shared state root (per Rule 1 / P2): COS_STATE_DIR overrides; default .coding-os/.
STATE_DIR = Path(os.environ.get("COS_STATE_DIR", str(PROJECT_ROOT / ".coding-os")))


def _resolve_agent_dir() -> Path | None:
    """
    Per-agent state lives in .coding-os/<agent>/ — never .claude/ (Rule 1).
    Prefer COS_AGENT_DIR; otherwise pick the most recently modified subdir
    of STATE_DIR that contains a .session-id file. Returns None if undecidable.
    """
    explicit = os.environ.get("COS_AGENT_DIR")
    if explicit:
        return Path(explicit)
    if not STATE_DIR.exists():
        return None
    candidates = [p for p in STATE_DIR.iterdir() if p.is_dir() and (p / ".session-id").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p / ".session-id").stat().st_mtime)


REQUIRED_HOOKS = [
    "thinking_os-gate.sh",
    "enforce-task-start.sh",
    "enforce-skill.sh",
    "enforce-zoom.sh",
    "block-secrets.sh",
    "block-dangerous-commands.sh",
    "block-protected-files.sh",
    "block-bad-patterns.sh",
    "capture-observation.sh",
    "session-end.sh",
    "write-state.sh",
    "check-state.sh",
]

LEARNING_TABLES = [
    "task_outcomes",
    "learned_patterns",
    "agent_metrics",
    "routing_weights",
    "experiment_log",
    "outcome_history",
]

ACTIVE_TABLES = [
    "observations",
    "concept_graph",
    "session_summaries",
]


# ── Check Functions ──────────────────────────────────────────────


def check_database() -> dict:
    """Check database health: existence, schema, table counts, null ratios."""
    result: dict = {"status": "PASS", "issues": [], "stats": {}}

    if not DEFAULT_DB_PATH.exists():
        result["status"] = "FAIL"
        result["issues"].append("Database file not found")
        return result

    # File size
    db_size = DEFAULT_DB_PATH.stat().st_size
    result["stats"]["db_size_mb"] = round(db_size / (1024 * 1024), 2)

    conn = get_connection()
    try:
        # Schema version
        version = get_schema_version(conn)
        result["stats"]["schema_version"] = version
        if version < 4:
            result["status"] = "WARN"
            result["issues"].append(f"Schema version {version} < 4 — missing brain features")

        # FTS5
        result["stats"]["fts5_available"] = has_fts5(conn)

        # Table counts
        stats = get_db_stats(conn)
        result["stats"]["tables"] = stats["tables"]

        # Check active tables have data
        for table in ACTIVE_TABLES:
            count = stats["tables"].get(table, 0) or 0
            if count == 0:
                result["status"] = "WARN"
                result["issues"].append(f"Active table '{table}' is empty")

        # Check learning tables status
        learning_active = 0
        for table in LEARNING_TABLES:
            count = stats["tables"].get(table, 0) or 0
            if count > 0:
                learning_active += 1
        result["stats"]["learning_tables_active"] = learning_active
        result["stats"]["learning_tables_total"] = len(LEARNING_TABLES)
        if learning_active == 0:
            result["issues"].append(
                "Self-learning pipeline not activated (0 learning tables have data)"
            )

        # Session summaries null ratio
        row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN request IS NULL THEN 1 ELSE 0 END) as null_request, "
            "SUM(CASE WHEN learned IS NULL THEN 1 ELSE 0 END) as null_learned, "
            "SUM(CASE WHEN completed IS NULL THEN 1 ELSE 0 END) as null_completed "
            "FROM session_summaries"
        ).fetchone()
        total = row[0] or 0
        if total > 0:
            null_ratio = round((row[1] + row[2] + row[3]) / (total * 3) * 100, 1)
            result["stats"]["session_null_ratio_pct"] = null_ratio
            if null_ratio > 80:
                result["issues"].append(
                    f"Session summaries {null_ratio}% null semantic fields (request/learned/completed)"
                )

        # Observations narrative null ratio (split: old vs recent)
        obs_row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN narrative IS NULL OR narrative = '' THEN 1 ELSE 0 END) as null_narrative "
            "FROM observations"
        ).fetchone()
        obs_total = obs_row[0] or 0
        if obs_total > 0:
            narrative_null = round(obs_row[1] / obs_total * 100, 1)
            result["stats"]["observations_narrative_null_pct"] = narrative_null

        # Recent narrative fill rate (last 24h) — shows if pipeline is working NOW
        recent_row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN narrative IS NOT NULL AND narrative != '' THEN 1 ELSE 0 END) as has_narrative "
            "FROM observations WHERE created_at >= datetime('now', '-24 hours')"
        ).fetchone()
        recent_total = recent_row[0] or 0
        if recent_total > 0:
            recent_fill = round(recent_row[1] / recent_total * 100, 1)
            result["stats"]["recent_narrative_fill_pct"] = recent_fill
        else:
            result["stats"]["recent_narrative_fill_pct"] = None

        # Concept graph edge type diversity
        edge_types_row = conn.execute(
            "SELECT COUNT(DISTINCT edge_type) FROM concept_graph"
        ).fetchone()
        result["stats"]["concept_edge_types"] = edge_types_row[0] or 0

        # Pipeline flow check: task_outcomes → learn_extract readiness
        outcome_count = stats["tables"].get("task_outcomes", 0) or 0
        result["stats"]["learn_extract_ready"] = outcome_count >= 3
        if outcome_count >= 3 and (stats["tables"].get("learned_patterns", 0) or 0) == 0:
            result["issues"].append(
                f"Pipeline gap: {outcome_count} task_outcomes but 0 learned_patterns — run cos_learn_extract"
            )

    finally:
        conn.close()

    return result


def check_hooks() -> dict:
    """Check hook files exist, are executable, and pass syntax check."""
    result: dict = {"status": "PASS", "issues": [], "hooks": {}}

    for hook_name in REQUIRED_HOOKS:
        hook_path = HOOKS_DIR / hook_name
        hook_info: dict = {"exists": False, "executable": False, "syntax_ok": False}

        if hook_path.exists():
            hook_info["exists"] = True
            hook_info["executable"] = os.access(hook_path, os.X_OK)

            # Syntax check
            try:
                subprocess.run(
                    ["bash", "-n", str(hook_path)],
                    capture_output=True,
                    timeout=5,
                    check=True,
                )
                hook_info["syntax_ok"] = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                hook_info["syntax_ok"] = False
                result["status"] = "FAIL"
                result["issues"].append(f"Hook '{hook_name}' has syntax errors")

            if not hook_info["executable"]:
                result["issues"].append(f"Hook '{hook_name}' is not executable")
        else:
            result["status"] = "FAIL"
            result["issues"].append(f"Required hook '{hook_name}' is missing")

        result["hooks"][hook_name] = hook_info

    # Functional hook tests now live in the pytest suite (tests/test_hooks_*.py),
    # not the retired bash test-hooks.sh harness. Probe that instead.
    hook_tests = list((PROJECT_ROOT / "tests").glob("test_hooks_*.py"))
    result["test_suite_exists"] = bool(hook_tests)
    if not hook_tests:
        result["issues"].append("no tests/test_hooks_*.py — no functional hook tests")

    return result


def check_gates() -> dict:
    """Check gate state files and session consistency."""
    result: dict = {"status": "PASS", "issues": [], "gates": {}}

    agent_dir = _resolve_agent_dir()
    if agent_dir is None:
        result["session_id"] = None
        result["issues"].append(
            "No agent dir (.coding-os/<agent>/) found — session tracking inactive"
        )
        return result

    # Session ID — agent-scoped (Rule 5)
    session_file = agent_dir / ".session-id"
    if session_file.exists():
        result["session_id"] = session_file.read_text().strip()
    else:
        result["session_id"] = None
        result["issues"].append(f"No .session-id in {agent_dir} — session tracking inactive")

    # Gate files — all agent-scoped per Rule 5
    gate_files = {
        "thinking_os-gate": ".thinking_os-gate",
        "task-current": ".task-current",
        "active-skill": ".active-skill",
        "zoom-checkpoint": ".zoom-checkpoint",
    }

    for name, filename in gate_files.items():
        gate_path = agent_dir / filename
        gate_info: dict = {
            "exists": False,
            "value": None,
            "session_match": False,
            "age_minutes": None,
        }

        if gate_path.exists():
            gate_info["exists"] = True
            content = gate_path.read_text().strip()
            parts = content.split(maxsplit=1)

            if len(parts) >= 2:
                file_session = parts[0]
                gate_info["value"] = parts[1]
                gate_info["session_match"] = (
                    result.get("session_id") is not None and file_session == result["session_id"]
                )

            # Age
            mtime = gate_path.stat().st_mtime
            age_min = (datetime.now(tz=timezone.utc).timestamp() - mtime) / 60
            gate_info["age_minutes"] = round(age_min, 1)

            if age_min > 120:
                gate_info["stale"] = True

        result["gates"][name] = gate_info

    return result


def check_learning_pipeline() -> dict:
    """Check if the learning pipeline components are wired and functional."""
    result: dict = {"status": "PASS", "issues": [], "components": {}}

    # Check Python scripts exist
    scripts = [
        ("capture.py", "Observation capture"),
        ("record_outcome.py", "Task outcome recording"),
        ("session_summary.py", "Session summary builder"),
        ("decay.py", "Confidence decay"),
        ("compress.py", "Observation compression"),
        ("impact.py", "Impact scoring"),
        ("concepts.py", "Concept extraction"),
        ("graph.py", "Concept graph"),
        ("dashboard.py", "Dashboard"),
    ]

    tos_dir = Path(__file__).resolve().parent
    for script, description in scripts:
        script_path = tos_dir / script
        result["components"][script] = {
            "exists": script_path.exists(),
            "description": description,
        }
        if not script_path.exists():
            result["issues"].append(f"Missing component: {script} ({description})")

    # Check if task-done wiring exists. Modern path: src/cli/board_commands.py
    # calls record_outcome via _record_brain_outcome_safe. Legacy path:
    # src/core/scripts/task-done.sh or infrastructure/scripts/task-done.sh.
    task_done_candidates = [
        PROJECT_ROOT / "src" / "cli" / "board_commands.py",
        *PROJECT_ROOT.glob("src/core/scripts/task-done*"),
        *PROJECT_ROOT.glob("infrastructure/scripts/task-done*"),
    ]
    found_outcome_call = False
    for script in task_done_candidates:
        if script.exists():
            content = script.read_text()
            if "record_outcome" in content:
                found_outcome_call = True
                break
    result["components"]["task_done_wired"] = found_outcome_call
    if not found_outcome_call:
        result["issues"].append(
            "task-done wiring missing: cli/board_commands.py does not call record_outcome",
        )

    # Check if session-end calls session_summary
    session_end = HOOKS_DIR / "session-end.sh"
    if session_end.exists():
        content = session_end.read_text()
        result["components"]["session_end_wired"] = "session_summary" in content
        if "session_summary" not in content:
            result["issues"].append("session-end.sh doesn't call session_summary.py")
    else:
        result["components"]["session_end_wired"] = False

    # Check if cos_learn_extract has any trigger
    # (This is called by MCP, so we check if thinking_os MCP server is configured)
    mcp_config = PROJECT_ROOT / ".mcp.json"
    if mcp_config.exists():
        try:
            mcp_data = json.loads(mcp_config.read_text())
            servers = mcp_data.get("mcpServers", {})
            # The server is registered as 'coding-os' (the cos_* tool
            # namespace); 'thinking_os' was the pre-rename key. Accept either
            # so this check stops false-negative'ing on every modern repo.
            result["components"]["mcp_server_configured"] = any(
                key in ("coding-os", "thinking_os") for key in servers
            )
        except (json.JSONDecodeError, KeyError):
            result["components"]["mcp_server_configured"] = False
    else:
        result["components"]["mcp_server_configured"] = False

    return result


# ── Main ──────��──────────────────��───────────────────────────────


def run_all_checks() -> dict:
    """Run all health checks and return combined results."""
    results = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "database": check_database(),
        "hooks": check_hooks(),
        "gates": check_gates(),
        "learning_pipeline": check_learning_pipeline(),
    }

    # Overall status
    statuses = [results[k]["status"] for k in ("database", "hooks", "gates", "learning_pipeline")]
    if "FAIL" in statuses:
        results["overall"] = "FAIL"
    elif "WARN" in statuses:
        results["overall"] = "WARN"
    else:
        results["overall"] = "PASS"

    # Collect all issues
    all_issues = []
    for section in ("database", "hooks", "gates", "learning_pipeline"):
        for issue in results[section].get("issues", []):
            all_issues.append(f"[{section}] {issue}")
    results["all_issues"] = all_issues

    return results


def main() -> None:
    results = run_all_checks()

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_human_readable(results)

    if results["overall"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
