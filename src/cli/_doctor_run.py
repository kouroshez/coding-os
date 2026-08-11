"""Private sibling of cli.doctor — the check-orchestration sequence; import cli.doctor."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from ._doctor_shared import (
    MANIFEST_PATH_DEFAULT,
    SEV_PASS,
    CheckResult,
    DoctorReport,
    _tick,
)
from .doctor_checks_core import (
    _check_config,
    _check_core_version,
    _check_database,
    _check_scaffold_roots,
    _check_state_dir,
)
from .doctor_checks_modules import (
    _check_hub_code_fresh,
    _check_module_command_drift,
    _check_module_consistency,
    _check_module_doc_drift,
    _check_module_rule_drift,
    _check_module_skill_drift,
    _check_runtime_errors,
    _check_subsystems_state_integrity,
)
from .doctor_checks_quality import _check_file_size_budget
from .doctor_checks_registry import (
    _check_agents_md_present,
    _check_category_balance,
    _check_mcp_actually_launches,
    _check_mcp_portable,
    _check_stack_registry_consistency,
    _check_stack_skills_linked,
)
from .doctor_checks_runtime import (
    _check_cognition_registries,
    _check_hook_coverage,
    _check_presence_zombies,
    _check_scheduled,
)
from .doctor_checks_scaffold import (
    _check_adapter,
    _check_manifest,
    _check_mcp_selftest,
    _check_placeholders,
    _ignore_globs_from_config,
    _suppress_checks,
)


def run_doctor(
    project: Path,
    *,
    manifest_path: Path | None = None,
    extra_ignores: list[str] | None = None,
) -> DoctorReport:
    """Run all implemented doctor checks and return a report."""
    report = DoctorReport(project_dir=str(project), agent=None, templates=[])
    config = _check_config(project, report)
    if config is None:
        return report
    state = _check_state_dir(project, config, report)
    graph_conn = None
    if state.is_dir():
        _tick("database + migrations")
        conn = _check_database(state, report)
        if conn is not None:
            with contextlib.closing(conn):
                pass
        _check_core_version(state, report)
        # Open a second short-lived connection for graph checks so
        # the first handle's contextlib.closing is not disturbed.
        try:
            import sqlite3 as _sqlite3

            db_file = state / "coding-os.db"
            if db_file.exists():
                graph_conn = _sqlite3.connect(str(db_file))
        except Exception as exc:
            logger = logging.getLogger("coding_os.doctor")
            logger.debug("graph doctor connection failed: %s", exc)
    _check_scaffold_roots(project, report)
    _tick("file-size budget")
    _check_file_size_budget(project, report)
    _check_adapter(project, report.agent, report)
    _tick("scanning scaffold manifest")
    _check_manifest(project, report, manifest_path or MANIFEST_PATH_DEFAULT)
    _tick("scanning for placeholders")
    _check_placeholders(project, report)
    _tick("MCP self-test (up to 30s)")
    _check_mcp_selftest(project, report)
    _check_stack_registry_consistency(report)
    _check_category_balance(report)
    _tick("stack skills linkage")
    _check_stack_skills_linked(project, report)
    _tick("MCP portability")
    _check_mcp_portable(project, report)
    _tick("MCP launch handshake (up to 20s)")
    _check_mcp_actually_launches(project, report)
    _check_agents_md_present(project, report)
    _tick("cognition registries")
    _check_cognition_registries(project, report)
    _tick("hook coverage")
    _check_hook_coverage(project, report)
    _check_module_consistency(project, report)
    _check_module_skill_drift(project, report)
    _check_module_command_drift(project, report)
    _check_module_rule_drift(project, report)
    _check_module_doc_drift(project, report)
    _check_subsystems_state_integrity(project, report)
    _tick("runtime errors")
    _check_runtime_errors(state, report)
    # graph_os health checks.
    _tick("graph_os health")
    try:
        from cli.doctor_graph import run_graph_checks

        # Module-aware (TASK-439): a project that disabled the graph module must
        # not be nagged to run graph-reindex on an intentionally-empty graph.
        from cli.subsystems import module_state

        if module_state(project).get("graph", True):
            run_graph_checks(report, state, graph_conn)
        else:
            report.checks.append(
                CheckResult(
                    "graph.module", SEV_PASS, "graph module disabled — skipping graph health"
                )
            )
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("graph doctor unavailable: %s", exc)
    finally:
        if graph_conn is not None:
            try:
                graph_conn.close()
            except Exception as exc:
                logger = logging.getLogger("coding_os.doctor")
                logger.debug("graph_conn close suppressed: %s", exc)
    # board_os health checks.
    _tick("board_os health")
    try:
        from cli.doctor_board import run_board_checks

        run_board_checks(report, project, state)
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("board doctor unavailable: %s", exc)
    _check_scheduled(project, report)
    _check_presence_zombies(project, report)
    _tick("hub code freshness")
    _check_hub_code_fresh(report)
    try:
        from cli.doctor_extras import run_extra_checks

        run_extra_checks(project, report)
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("doctor_extras unavailable: %s", exc)
    ignore_globs = _ignore_globs_from_config(config)
    if extra_ignores:
        ignore_globs.extend(extra_ignores)
    suppressed = _suppress_checks(report, ignore_globs)
    if suppressed > 0:
        report.suppressed = suppressed
        report.suppressed_globs = ignore_globs
    return report
