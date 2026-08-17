"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor.

The four runtime checks live in leaves — cognition registries, hook coverage,
presence zombies, and the nightly schedule — and are re-exported here so the
kernel's import list is unchanged.
"""

from __future__ import annotations

from ._doctor_cognition import _check_cognition_registries as _check_cognition_registries
from ._doctor_hook_coverage import _check_hook_coverage as _check_hook_coverage
from ._doctor_presence import _check_presence_zombies as _check_presence_zombies
from ._doctor_schedule import _check_scheduled as _check_scheduled
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
from ._doctor_supervision import _check_supervision_policy as _check_supervision_policy
