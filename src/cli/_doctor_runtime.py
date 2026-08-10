"""Doctor checks for this machine's runtime: extras, state size, importability, CLI.

Answers "can the tools actually run here?" — the checks that fail when an
install is incomplete or a state file has grown past its budget.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from cli.doctor import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)

logger = logging.getLogger("coding_os.doctor.extras")


# ---------------------------------------------------------------------------
# runtime.optional_extras_installed — optional_extras_installed
# ---------------------------------------------------------------------------

OPTIONAL_EXTRA_IMPORTS: dict[str, tuple[str, str]] = {
    "claude-sdk": ("claude_agent_sdk", "real claude sub-agent dispatch (cos_dispatch_formula_run)"),
    "web": ("fastapi", "hub web server (cos hub start, port 9188)"),
    "rag": ("sentence_transformers", "doc embeddings + cos_doc_search semantic mode"),
    "graph_os": ("tree_sitter", "polyglot graph extractors (tree-sitter parsers)"),
    "board_os": ("aiohttp", "board live viewer (cos board --web)"),
}


def _check_optional_extras_installed(project: Path, report: DoctorReport) -> None:
    """runtime.optional_extras_installed — every extra whose feature is active is importable."""
    missing: list[dict[str, str]] = []
    for extra_name, (module_name, feature_description) in OPTIONAL_EXTRA_IMPORTS.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(
                {"extra": extra_name, "module": module_name, "feature": feature_description}
            )
    if missing:
        import sys

        _in_tool = "uv" in sys.executable and "tools" in sys.executable
        fix_cmd = (
            "uv tool install --editable . --all-extras" if _in_tool else "uv sync --all-extras"
        )
        report.checks.append(
            CheckResult(
                "runtime.optional_extras_installed",
                SEV_WARN,
                f"{len(missing)} optional extra(s) not installed — features unavailable",
                {"missing": missing, "fix": fix_cmd},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "runtime.optional_extras_installed",
                SEV_PASS,
                f"all {len(OPTIONAL_EXTRA_IMPORTS)} optional extras importable",
            )
        )


# ---------------------------------------------------------------------------
# state.size_within_budget — runtime_state_within_budget
# Catches runaway DB / WAL growth that silently degrades MCP latency.
# ---------------------------------------------------------------------------

DATABASE_FILE_RELATIVE_PATH = ".coding-os/coding-os.db"
WRITE_AHEAD_LOG_RELATIVE_PATH = ".coding-os/coding-os.db-wal"
DATABASE_SIZE_BUDGET_MEGABYTES = 200
WRITE_AHEAD_LOG_BUDGET_MEGABYTES = 50


def _check_runtime_state_within_budget(project: Path, report: DoctorReport) -> None:
    """state.size_within_budget — coding-os.db and its WAL stay within size budgets."""
    database_path = project / DATABASE_FILE_RELATIVE_PATH
    write_ahead_log_path = project / WRITE_AHEAD_LOG_RELATIVE_PATH
    findings: list[dict[str, Any]] = []

    if database_path.exists():
        database_megabytes = database_path.stat().st_size / (1024 * 1024)
        if database_megabytes > DATABASE_SIZE_BUDGET_MEGABYTES:
            findings.append(
                {
                    "file": DATABASE_FILE_RELATIVE_PATH,
                    "actual_megabytes": round(database_megabytes, 1),
                    "budget_megabytes": DATABASE_SIZE_BUDGET_MEGABYTES,
                    "fix": "review brain memory growth — `cos brain stats`",
                }
            )

    if write_ahead_log_path.exists():
        write_ahead_log_megabytes = write_ahead_log_path.stat().st_size / (1024 * 1024)
        if write_ahead_log_megabytes > WRITE_AHEAD_LOG_BUDGET_MEGABYTES:
            findings.append(
                {
                    "file": WRITE_AHEAD_LOG_RELATIVE_PATH,
                    "actual_megabytes": round(write_ahead_log_megabytes, 1),
                    "budget_megabytes": WRITE_AHEAD_LOG_BUDGET_MEGABYTES,
                    "fix": "checkpoint: sqlite3 coding-os.db 'PRAGMA wal_checkpoint(TRUNCATE)'",
                }
            )

    if findings:
        report.checks.append(
            CheckResult(
                "state.size_within_budget",
                SEV_WARN,
                f"{len(findings)} runtime file(s) exceed budget",
                {"findings": findings},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "state.size_within_budget",
                SEV_PASS,
                "runtime DB + WAL within budget",
            )
        )


# ---------------------------------------------------------------------------
# mcp.dispatcher_modules_importable — dispatcher_modules_importable
# Cognition pipeline modules must import — if any breaks, role chains fail
# silently with `claude_agent_sdk not installed` (which is misleading).
# ---------------------------------------------------------------------------

COGNITION_DISPATCHER_MODULES = (
    "thinking_os.dispatcher",
    "thinking_os.dispatchers.default",
)


def _check_dispatcher_modules_importable(_project: Path, report: DoctorReport) -> None:
    """mcp.dispatcher_modules_importable — every cognition dispatcher module imports without error."""
    import_failures: list[dict[str, str]] = []
    for module_name in COGNITION_DISPATCHER_MODULES:
        try:
            __import__(module_name)
        except Exception as exc:
            import_failures.append(
                {
                    "module": module_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    if import_failures:
        report.checks.append(
            CheckResult(
                "mcp.dispatcher_modules_importable",
                SEV_FAIL,
                f"{len(import_failures)} dispatcher module(s) failed to import",
                {"failures": import_failures},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "mcp.dispatcher_modules_importable",
                SEV_PASS,
                f"all {len(COGNITION_DISPATCHER_MODULES)} dispatcher modules importable",
            )
        )


# ---------------------------------------------------------------------------
# mcp.envelope_contract_sample — mcp_envelope_contract_sample
# Sample a few cos_* tools, verify each returns the {ok, data} or
# {ok: false, error} envelope. Drift here silently breaks agent retrieval.
# ---------------------------------------------------------------------------

ENVELOPE_SAMPLE_TOOLS = (
    "core.thinking_os.tools.memory",
    "core.thinking_os.tools.tasks",
    "core.thinking_os.tools.retrieve",
)


def _check_mcp_envelope_contract_sample(_project: Path, report: DoctorReport) -> None:
    """mcp.envelope_contract_sample — sample MCP tool modules import and expose `ok`/`fail` envelope helpers."""
    contract_failures: list[dict[str, str]] = []
    sampled = 0
    for module_name in ENVELOPE_SAMPLE_TOOLS:
        try:
            __import__(module_name, fromlist=["_shared"])
            sampled += 1
        except ImportError as exc:
            contract_failures.append({"module": module_name, "error": str(exc)})
            continue

    try:
        envelope_module = __import__("core.thinking_os.tools._shared", fromlist=["ok", "fail"])
        for helper_name in ("ok", "fail", "safe_tool"):
            if not hasattr(envelope_module, helper_name):
                contract_failures.append(
                    {
                        "module": "core.thinking_os.tools._shared",
                        "error": f"missing helper {helper_name!r}",
                    }
                )
    except ImportError as exc:
        contract_failures.append(
            {
                "module": "core.thinking_os.tools._shared",
                "error": str(exc),
            }
        )

    if contract_failures:
        report.checks.append(
            CheckResult(
                "mcp.envelope_contract_sample",
                SEV_FAIL,
                f"{len(contract_failures)} envelope contract violation(s)",
                {"failures": contract_failures},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "mcp.envelope_contract_sample",
                SEV_PASS,
                f"sampled {sampled} tool module(s); envelope helpers exposed",
            )
        )


# ---------------------------------------------------------------------------
# runtime.cli_binary_health — cli_binary_health
# Detects stale globally-installed `cos` shim after editable-install changes.
# A user running `cos` from a stale path gets `ModuleNotFoundError: cli`,
# which is exactly the failure mode caught after the src-layout migration.
# ---------------------------------------------------------------------------


def _check_cli_binary_health(_project: Path, report: DoctorReport) -> None:
    """runtime.cli_binary_health — global `cos` binary points to a working editable install."""
    cos_binary_path = shutil.which("cos")
    if cos_binary_path is None:
        report.checks.append(
            CheckResult(
                "runtime.cli_binary_health",
                SEV_WARN,
                "no `cos` binary on PATH (consider `uv tool install --editable .`)",
            )
        )
        return

    # Quick import-resolution check: invoke the binary with --version and
    # capture any tracebacks that point at the missing-module symptom.
    import subprocess

    try:
        completed_process = subprocess.run(
            [cos_binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report.checks.append(
            CheckResult(
                "runtime.cli_binary_health",
                SEV_FAIL,
                f"`cos --version` failed: {exc}",
                {"binary": cos_binary_path, "fix": "uv tool install --editable . --force"},
            )
        )
        return

    if completed_process.returncode != 0 or "ModuleNotFoundError" in (
        completed_process.stderr or ""
    ):
        report.checks.append(
            CheckResult(
                "runtime.cli_binary_health",
                SEV_FAIL,
                "`cos` binary fails to import its package (stale shim)",
                {
                    "binary": cos_binary_path,
                    "stderr_tail": (completed_process.stderr or "")[-300:],
                    "fix": "uv tool install --editable . --force",
                },
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "runtime.cli_binary_health",
                SEV_PASS,
                f"`cos --version` works ({completed_process.stdout.strip()})",
                {"binary": cos_binary_path},
            )
        )
