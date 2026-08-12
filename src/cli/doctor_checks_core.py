"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from cli.core_version import current_core_version, read_stamped_version, upgrade_command

from ._doctor_shared import (  # noqa: F401
    _DOCTOR_CFG,
    CODING_OS_ROOT,
    CONFIG_FILE,
    EXPECTED_SCHEMA_VERSION,
    EXPECTED_TABLES,
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

logger = logging.getLogger(__name__)


def _check_config(project: Path, report: DoctorReport) -> dict[str, Any] | None:
    """config.file_present — .coding-os.yaml exists and parses. Fatal if missing."""
    config_path = project / CONFIG_FILE
    if not config_path.exists():
        report.checks.append(
            CheckResult(
                "config.file_present",
                SEV_FAIL,
                f"{CONFIG_FILE} not found — run `cos init --agent <claude|codex>`",
                {"path": str(config_path)},
            )
        )
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        report.checks.append(
            CheckResult(
                "config.file_present",
                SEV_FAIL,
                f"{CONFIG_FILE} is not valid YAML: {exc}",
                {"path": str(config_path)},
            )
        )
        return None
    report.checks.append(
        CheckResult("config.file_present", SEV_PASS, "valid", {"keys": sorted(data.keys())})
    )
    report.agent = (data.get("agents") or [None])[0]
    report.templates = list(data.get("templates") or [])
    return data


def _check_state_dir(project: Path, config: dict[str, Any], report: DoctorReport) -> Path:
    """state.directory_present — state dir exists."""
    state = project / config.get("state_dir", STATE_DIR_DEFAULT)
    if not state.is_dir():
        report.checks.append(
            CheckResult(
                "state.directory_present",
                SEV_FAIL,
                "state directory missing",
                {"path": str(state)},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "state.directory_present",
                SEV_PASS,
                "present",
                {"path": str(state)},
            )
        )
    return state


def _check_database(state: Path, report: DoctorReport) -> sqlite3.Connection | None:
    """database.openable + database.schema_current + database.tables_present — DB opens, schema version 6, all 11 tables present."""
    db_path = state / "coding-os.db"
    if not db_path.exists():
        report.checks.append(
            CheckResult(
                "database.openable",
                SEV_FAIL,
                "coding-os.db not found",
                {"path": str(db_path)},
            )
        )
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "database.openable",
                SEV_FAIL,
                f"cannot open DB: {exc}",
                {"path": str(db_path)},
            )
        )
        return None
    report.checks.append(
        CheckResult("database.openable", SEV_PASS, "opened", {"path": str(db_path)})
    )

    try:
        cur = conn.execute("SELECT MAX(version) FROM schema_version")
        row = cur.fetchone()
        version = int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "database.schema_current",
                SEV_FAIL,
                f"schema_version query failed: {exc}",
            )
        )
        version = None

    if version is None:
        pass  # already reported
    elif version < EXPECTED_SCHEMA_VERSION:
        report.checks.append(
            CheckResult(
                "database.schema_current",
                SEV_FAIL,
                f"schema version {version} < expected {EXPECTED_SCHEMA_VERSION}",
                {"actual": version, "expected": EXPECTED_SCHEMA_VERSION},
            )
        )
    elif version > EXPECTED_SCHEMA_VERSION:
        report.checks.append(
            CheckResult(
                "database.schema_current",
                SEV_WARN,
                f"schema version {version} newer than expected {EXPECTED_SCHEMA_VERSION}",
                {"actual": version, "expected": EXPECTED_SCHEMA_VERSION},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "database.schema_current",
                SEV_PASS,
                f"v{version}",
                {"actual": version},
            )
        )

    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual = {row[0] for row in cur.fetchall()}
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult("database.tables_present", SEV_FAIL, f"table list failed: {exc}")
        )
        return conn

    missing = sorted(EXPECTED_TABLES - actual)
    if missing:
        report.checks.append(
            CheckResult(
                "database.tables_present",
                SEV_FAIL,
                f"missing tables: {', '.join(missing)}",
                {"missing": missing, "found": sorted(actual)},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "database.tables_present",
                SEV_PASS,
                f"all {len(EXPECTED_TABLES)} core tables present",
                {"count": len(actual)},
            )
        )
    return conn


def _check_core_version(state: Path, report: DoctorReport) -> None:
    """core.version_stamp — consumer's stamped core version vs the installed core (D6 drift)."""
    current = current_core_version()
    stamped = read_stamped_version(state)
    if stamped is None:
        report.checks.append(
            CheckResult(
                "core.version_stamp",
                SEV_WARN,
                "no core-version stamp — scaffolded before stamping; run `cos update`",
                {"current": current},
            )
        )
    elif stamped != current:
        # `cos update` re-stamps the project to whatever is installed, so naming
        # it alone turns a stale install into a silenced warning. The package
        # upgrade is the step that actually moves the version.
        report.checks.append(
            CheckResult(
                "core.version_stamp",
                SEV_WARN,
                f"core drift — scaffolded by {stamped}, current core {current}; "
                f"upgrade the package (`{upgrade_command()}`), then run `cos update`",
                {"stamped": stamped, "current": current},
            )
        )
    else:
        report.checks.append(
            CheckResult("core.version_stamp", SEV_PASS, f"core {current}", {"stamped": stamped})
        )


def _check_scaffold_roots(project: Path, report: DoctorReport) -> None:
    """scaffold.roots_present — AGENTS.md, Makefile, docs/ exist at project root."""
    required = {
        "AGENTS.md": project / "AGENTS.md",
        "Makefile": project / "Makefile",
        "docs/": project / "docs",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        report.checks.append(
            CheckResult(
                "scaffold.roots_present",
                SEV_FAIL,
                f"missing: {', '.join(missing)}",
                {"missing": missing},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "scaffold.roots_present",
                SEV_PASS,
                "AGENTS.md, Makefile, docs/ all present",
            )
        )


# Top-level src/ subtrees the project anatomy permits (project-anatomy.md).
# Stacks own backend/services/frontend/mobile; shared/ is the polyglot reuse
# layer. Anything else directly under src/ is a stray subtree.
_ANATOMY_TOP_LEVEL = ("backend", "services", "frontend", "mobile", "shared")


def _declared_src_segments(project: Path, config: dict[str, Any] | None) -> set[str]:
    """Top-level `src/<seg>/` segments each installed stack owns per the
    aggregated scaffold-boundary.yaml — e.g. {"services", "frontend"} after
    multi-backend relocation, or {"backend"} for a single backend. Empty when
    no boundary file exists (fall back to the static anatomy allow-list)."""
    state_name = (config or {}).get("state_dir", STATE_DIR_DEFAULT)
    boundary = project / state_name / "scaffold-boundary.yaml"
    if not boundary.is_file():
        return set()
    try:
        data = yaml.safe_load(boundary.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    segments: set[str] = set()
    for stack in data.get("stacks") or []:
        for root in stack.get("roots") or []:
            parts = str(root).strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "src":
                segments.add(parts[1])
    return segments


def _check_structure(
    project: Path, report: DoctorReport, config: dict[str, Any] | None = None
) -> None:
    """structure.* — validate the src/ tree against the declared project anatomy.

    A compliant tree appends only PASS (exit 0). Each stray subtree — a
    `src/<name>/` that is neither `shared` nor a declared/known anatomy root —
    becomes one FAIL naming the expected location, so the exit code is 1."""
    src = project / "src"
    if not src.is_dir():
        report.checks.append(
            CheckResult("structure.src_present", SEV_PASS, "no src/ tree — nothing to validate")
        )
        return

    # Only a project that DECLARED an anatomy (installed stacks → aggregated
    # scaffold-boundary.yaml) is validated. A base-only consumer or a non-
    # consumer tree (e.g. the meta-repo itself) never declared one, so there is
    # nothing to validate against — emit PASS rather than flag its own layout.
    state_name = (config or {}).get("state_dir", STATE_DIR_DEFAULT)
    if not (project / state_name / "scaffold-boundary.yaml").is_file():
        report.checks.append(
            CheckResult(
                "structure.not_declared",
                SEV_PASS,
                "no scaffold-boundary.yaml — no declared anatomy to validate",
            )
        )
        return

    # `declared` (from the aggregated boundary) is used ONLY to detect the
    # services/ layout — so a top-level src/backend/ in a project that placed
    # its backends under src/services/ is flagged as misplaced. The five known
    # anatomy slots are always permitted, so a hand-added src/frontend/ without
    # a registered frontend stack is never a false positive.
    declared = _declared_src_segments(project, config)
    services_layout = "services" in declared
    known = set(_ANATOMY_TOP_LEVEL)

    stray = 0
    for child in sorted(p for p in src.iterdir() if p.is_dir()):
        name = child.name
        if services_layout and name == "backend":
            expected = (
                "src/services/<stack-id>/ — this project uses the services/ "
                "layout, so a top-level src/backend/ is misplaced"
            )
        elif name in known:
            continue
        else:
            expected = (
                f"a declared anatomy subtree ({', '.join(_ANATOMY_TOP_LEVEL)}); "
                "services under src/services/<name>/, shared code under src/shared/"
            )
        report.checks.append(
            CheckResult(
                f"structure.stray.{name}",
                SEV_FAIL,
                f"src/{name}/ violates declared anatomy — expected: {expected}",
                {"path": f"src/{name}", "expected": expected},
            )
        )
        stray += 1

    if stray == 0:
        report.checks.append(
            CheckResult(
                "structure.anatomy",
                SEV_PASS,
                "src/ tree matches the declared anatomy",
                {"known": sorted(known)},
            )
        )
