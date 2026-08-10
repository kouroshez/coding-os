"""Extended doctor checks — covers gaps surfaced after the src-layout migration.

Facade: `run_extra_checks` is the single entry `run_doctor()` calls, and it runs
each check in order, isolating failures so one raising check never hides the
rest. The checks themselves are grouped by what they inspect — the machine's
runtime, the installed adapters, or the project's own content.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cli.doctor import (
    SEV_WARN,
    CheckResult,
    DoctorReport,
)

from ._doctor_adapters import (
    _check_adapter_dir_symlinks_healthy,
    _check_agent_identity_file,
    _check_all_installed_adapters_healthy,
    _check_consumer_project_hook_symlinks,
    _check_hooks_source_cos_env,
    _normalized_hook_map as _normalized_hook_map,
)
from ._doctor_project import (
    _check_board_config_yamls_valid,
    _check_graph_uid_consistency,
    _check_hub_http_responds,
    _check_markdown_link_integrity,
    _check_regen_artifact_freshness,
    _check_registered_project_paths_exist,
    _check_scaffold_boundary_yamls_valid,
)
from ._doctor_runtime import (
    _check_cli_binary_health,
    _check_dispatcher_modules_importable,
    _check_mcp_envelope_contract_sample,
    _check_optional_extras_installed,
    _check_runtime_state_within_budget,
)

logger = logging.getLogger("coding_os.doctor.extras")


# ---------------------------------------------------------------------------
# Entry point — called from cli.doctor.run_doctor()
# ---------------------------------------------------------------------------


def run_extra_checks(project: Path, report: DoctorReport) -> None:
    """Run runtime.optional_extras_installed-hook.cos_env_sourced. Each appends one CheckResult; failures never raise."""
    for check_function in (
        _check_optional_extras_installed,
        _check_all_installed_adapters_healthy,
        _check_hub_http_responds,
        _check_markdown_link_integrity,
        _check_graph_uid_consistency,
        _check_regen_artifact_freshness,
        _check_board_config_yamls_valid,
        _check_registered_project_paths_exist,
        _check_runtime_state_within_budget,
        _check_dispatcher_modules_importable,
        _check_mcp_envelope_contract_sample,
        _check_cli_binary_health,
        _check_scaffold_boundary_yamls_valid,
        _check_agent_identity_file,
        _check_adapter_dir_symlinks_healthy,
        _check_consumer_project_hook_symlinks,
        _check_hooks_source_cos_env,
    ):
        try:
            check_function(project, report)
        except Exception as exc:
            logger.debug("extra check %s raised: %s", check_function.__name__, exc)
            report.checks.append(
                CheckResult(
                    "doctor.check_failed",
                    SEV_WARN,
                    f"{check_function.__name__.lstrip('_')} raised unexpectedly: {exc}",
                    {"check_function": check_function.__name__},
                )
            )
