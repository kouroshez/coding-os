"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor.

The stack-registry checks live in `_doctor_stacks` and the MCP wiring checks in
`_doctor_mcp`; both are re-exported here so the kernel's import list is
unchanged. `docs.agents_md_present` stays because it belongs to neither.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ._doctor_mcp import (
    _check_mcp_actually_launches as _check_mcp_actually_launches,
    _check_mcp_portable as _check_mcp_portable,
    _load_coding_os_mcp_launch as _load_coding_os_mcp_launch,
)
from ._doctor_shared import (  # noqa: F401
    _DOCTOR_CFG,
    CODING_OS_ROOT,
    CONFIG_FILE,
    IGNORED_PREFIXES,
    MANIFEST_PATH_DEFAULT,
    MCP_SERVER_PATH,
    PLACEHOLDER_RE,
    RUNTIME_PATHS,
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    STATE_DIR_DEFAULT,
    CheckResult,
    DoctorReport,
    _derive_expected_schema_version,
    _load_doctor_config,
    _load_runtime_paths,
    _scan_project_files,
    _tick,
)
from ._doctor_stacks import (
    _check_category_balance as _check_category_balance,
    _check_stack_registry_consistency as _check_stack_registry_consistency,
    _check_stack_skills_linked as _check_stack_skills_linked,
)

logger = logging.getLogger(__name__)


def _check_agents_md_present(project: Path, report: DoctorReport) -> None:
    """docs.agents_md_present — AGENTS.md at the project root is the canonical instruction file.

    Read by both Claude (via AGENTS.md convention) and Codex. `cos init`
    generates it; pre-v0.2.0 projects or partial installs may be missing it.
    `cos add-adapter` and `cos update` now backfill automatically — this
    check catches projects that never ran either command since.
    """
    agents_md = project / "AGENTS.md"
    if agents_md.exists():
        report.checks.append(
            CheckResult(
                "docs.agents_md_present",
                SEV_PASS,
                "present",
                {"path": str(agents_md.relative_to(project))},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "docs.agents_md_present",
            SEV_FAIL,
            "missing — run 'cos update' or 'cos add-adapter <agent>' to backfill",
            {"expected": "AGENTS.md"},
        )
    )
