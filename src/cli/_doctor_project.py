"""Doctor checks for the project's own content: hub, docs, graph, board, registry.

These read the repository and its derived artifacts rather than the machine —
stale regen output, a broken markdown link, a registry entry pointing nowhere.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from cli.doctor import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)

logger = logging.getLogger("coding_os.doctor.extras")


# ---------------------------------------------------------------------------
# hub.http_responsive — hub_http_responds
# ---------------------------------------------------------------------------

HUB_DEFAULT_URL = "http://127.0.0.1:9188/"
HUB_TIMEOUT_SECONDS = 2.0


def _check_hub_http_responds(project: Path, report: DoctorReport) -> None:
    """hub.http_responsive — when hub is running on :9188, GET / returns 200."""
    try:
        with urllib.request.urlopen(HUB_DEFAULT_URL, timeout=HUB_TIMEOUT_SECONDS) as response:
            status_code = response.status
    except urllib.error.URLError as exc:
        report.checks.append(
            CheckResult(
                "hub.http_responsive",
                SEV_PASS,
                f"hub not running (skip): {exc.reason if hasattr(exc, 'reason') else exc}",
            )
        )
        return
    except (OSError, ValueError) as exc:
        report.checks.append(
            CheckResult(
                "hub.http_responsive",
                SEV_PASS,
                f"hub not reachable (skip): {exc}",
            )
        )
        return

    if status_code == 200:
        report.checks.append(
            CheckResult("hub.http_responsive", SEV_PASS, f"GET {HUB_DEFAULT_URL} returned 200")
        )
    else:
        report.checks.append(
            CheckResult(
                "hub.http_responsive",
                SEV_FAIL,
                f"GET {HUB_DEFAULT_URL} returned {status_code} (expected 200)",
                {"fix": "cos hub stop && cos hub start"},
            )
        )


# ---------------------------------------------------------------------------
# docs.markdown_link_integrity — markdown_link_integrity (AGENTS.md + README.md)
# ---------------------------------------------------------------------------

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\((?!https?://)([^)#]+\.md)")


def _check_markdown_link_integrity(project: Path, report: DoctorReport) -> None:
    """docs.markdown_link_integrity — markdown links to .md files in AGENTS.md + README.md resolve to existing files."""
    target_files = [project / "AGENTS.md", project / "README.md"]
    broken_links: list[dict[str, str]] = []
    checked_count = 0
    for source_file in target_files:
        if not source_file.is_file():
            continue
        text = source_file.read_text(encoding="utf-8", errors="ignore")
        for match in MARKDOWN_LINK_RE.finditer(text):
            checked_count += 1
            referenced_path = match.group(1).strip()
            if referenced_path.startswith("/"):
                resolved = Path(referenced_path)
            else:
                resolved = (source_file.parent / referenced_path).resolve()
            if not resolved.exists():
                broken_links.append(
                    {
                        "source": str(source_file.relative_to(project)),
                        "target": referenced_path,
                    }
                )

    if broken_links:
        report.checks.append(
            CheckResult(
                "docs.markdown_link_integrity",
                SEV_FAIL,
                f"{len(broken_links)} broken markdown link(s) in AGENTS.md/README.md",
                {"broken": broken_links[:10], "checked": checked_count},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "docs.markdown_link_integrity",
                SEV_PASS,
                f"all {checked_count} markdown link(s) resolve",
            )
        )


# ---------------------------------------------------------------------------
# graph.uid_consistency — graph_uid_consistency
# Catches stale legacy path prefixes (e.g. `core/` instead of `src/core/`)
# left behind after a directory rename. Re-index alone does not delete old
# UIDs, so this surfaces drift the prune step missed.
# ---------------------------------------------------------------------------

LEGACY_PATH_PREFIXES_AFTER_SRC_MIGRATION = (
    "code:file:core/",
    "code:file:cli/",
    "code:file:adapters/",
    "code:file:templates/",
    "code:file:scripts/",
    "folder:core",
    "folder:cli",
    "folder:adapters",
    "folder:templates",
    "folder:scripts",
)


def _check_graph_uid_consistency(project: Path, report: DoctorReport) -> None:
    """graph.uid_consistency — graph_nodes UIDs do not contain pre-src-migration path prefixes."""
    db_path = project / ".coding-os" / "coding-os.db"
    if not db_path.exists():
        report.checks.append(CheckResult("graph.uid_consistency", SEV_PASS, "no DB (skip)"))
        return
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_nodes'"
            )
            if cursor.fetchone() is None:
                report.checks.append(
                    CheckResult(
                        "graph.uid_consistency", SEV_PASS, "graph_nodes table absent (skip)"
                    )
                )
                return
            stale_count = 0
            for prefix in LEGACY_PATH_PREFIXES_AFTER_SRC_MIGRATION:
                cursor.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE uid LIKE ?",
                    (f"{prefix}%",),
                )
                stale_count += cursor.fetchone()[0]
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult("graph.uid_consistency", SEV_WARN, f"DB query failed: {exc}")
        )
        return

    if stale_count > 0:
        report.checks.append(
            CheckResult(
                "graph.uid_consistency",
                SEV_FAIL,
                f"{stale_count} graph node(s) with legacy pre-src-migration prefix",
                {"fix": "cos graph-reindex --force then `cos doctor` again"},
            )
        )
    else:
        report.checks.append(
            CheckResult("graph.uid_consistency", SEV_PASS, "no stale legacy-prefix UIDs")
        )


# ---------------------------------------------------------------------------
# scaffold.regen_artifacts_fresh — regen_artifact_freshness
# Derived artifacts (dimension-registry, skill-enforcement, manifest, adapter
# templates) must not be older than their source stack.yaml files. Drift here
# means `make regen-*` was skipped after a stack edit.
# ---------------------------------------------------------------------------

REGEN_ARTIFACT_DEPENDENCIES: dict[str, dict[str, Any]] = {
    "src/core/rules/dimension-registry.md": {
        "sources_glob": "src/templates/*/stack.yaml",
        "fix": "make regen-rules",
    },
    "src/core/rules/skill-enforcement.md": {
        "sources_glob": "src/templates/*/stack.yaml",
        "fix": "make regen-rules",
    },
    "src/core/scaffold_manifest.json": {
        "sources_glob": "src/templates/*/stack.yaml",
        "fix": "make manifest-regen",
    },
}


def _check_regen_artifact_freshness(project: Path, report: DoctorReport) -> None:
    """scaffold.regen_artifacts_fresh — derived artifacts are not older than their source files."""
    stale_artifacts: list[dict[str, Any]] = []
    for artifact_relative_path, spec in REGEN_ARTIFACT_DEPENDENCIES.items():
        artifact_path = project / artifact_relative_path
        if not artifact_path.exists():
            continue
        artifact_modified_time = artifact_path.stat().st_mtime
        source_paths = list(project.glob(spec["sources_glob"]))
        if not source_paths:
            continue
        newest_source_modified_time = max(
            source_path.stat().st_mtime for source_path in source_paths
        )
        if newest_source_modified_time > artifact_modified_time:
            stale_artifacts.append(
                {
                    "artifact": artifact_relative_path,
                    "fix": spec["fix"],
                    "lag_seconds": int(newest_source_modified_time - artifact_modified_time),
                }
            )

    if stale_artifacts:
        report.checks.append(
            CheckResult(
                "scaffold.regen_artifacts_fresh",
                SEV_WARN,
                f"{len(stale_artifacts)} derived artifact(s) older than source",
                {"stale": stale_artifacts},
            )
        )
    else:
        report.checks.append(
            CheckResult("scaffold.regen_artifacts_fresh", SEV_PASS, "all derived artifacts fresh")
        )


# ---------------------------------------------------------------------------
# board.config_yamls_valid — board_config_yamls_valid
# transition-gates.yaml + verify-suites.yaml must parse cleanly. Malformed
# board config causes cos task-move / cos verify to fail silently.
# ---------------------------------------------------------------------------

BOARD_CONFIG_RELATIVE_PATHS = (
    "src/core/board_os/transition-gates.yaml",
    "src/core/board_os/verify-suites.yaml",
)


def _check_board_config_yamls_valid(project: Path, report: DoctorReport) -> None:
    """board.config_yamls_valid — transition-gates.yaml + verify-suites.yaml parse as YAML."""
    parse_errors: list[dict[str, str]] = []
    parsed_count = 0
    for config_relative_path in BOARD_CONFIG_RELATIVE_PATHS:
        config_path = project / config_relative_path
        if not config_path.exists():
            continue
        try:
            yaml.safe_load(config_path.read_text(encoding="utf-8"))
            parsed_count += 1
        except yaml.YAMLError as exc:
            parse_errors.append(
                {
                    "path": config_relative_path,
                    "error": str(exc),
                }
            )

    if parse_errors:
        report.checks.append(
            CheckResult(
                "board.config_yamls_valid",
                SEV_FAIL,
                f"{len(parse_errors)} board config(s) failed to parse",
                {"errors": parse_errors},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "board.config_yamls_valid",
                SEV_PASS,
                f"all {parsed_count} board config(s) parse cleanly",
            )
        )


# ---------------------------------------------------------------------------
# hub.project_paths_exist — registered_project_paths_exist
# Hub registry stale entries (deleted dirs) bloat sync-doctor output and
# block clean automation. This check just flags them.
# ---------------------------------------------------------------------------


def _check_registered_project_paths_exist(project: Path, report: DoctorReport) -> None:
    """hub.project_paths_exist — every entry in ~/.coding-os/registry.json points to an existing dir."""
    registry_path = Path.home() / ".coding-os" / "registry.json"
    if not registry_path.exists():
        report.checks.append(
            CheckResult("hub.project_paths_exist", SEV_PASS, "no hub registry yet (skip)")
        )
        return
    try:
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        report.checks.append(
            CheckResult("hub.project_paths_exist", SEV_FAIL, f"registry.json unreadable: {exc}")
        )
        return

    registered_projects = registry_data.get("projects") or []
    missing_paths: list[dict[str, str]] = []
    for project_entry in registered_projects:
        registered_path = Path(project_entry.get("path", ""))
        if registered_path and not registered_path.exists():
            missing_paths.append(
                {
                    "slug": project_entry.get("slug", "(unnamed)"),
                    "path": str(registered_path),
                }
            )

    if missing_paths:
        report.checks.append(
            CheckResult(
                "hub.project_paths_exist",
                SEV_WARN,
                f"{len(missing_paths)} registered project path(s) missing on disk",
                {"missing": missing_paths},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "hub.project_paths_exist",
                SEV_PASS,
                f"all {len(registered_projects)} registered project path(s) exist",
            )
        )


# ---------------------------------------------------------------------------
# scaffold.boundary_yamls_valid — scaffold_boundary_yamls_valid
# Every stack ships scaffold-boundary.yaml. Aggregator at `cos init` rejects
# malformed entries, but doctor never gates them — broken boundary slips
# through until first multi-stack install.
# ---------------------------------------------------------------------------

REQUIRED_BOUNDARY_KEYS = (
    "version",
    "stack",
    "roots",
    "file_patterns",
    "imports_from",
    "forbids_writing_in",
)


def _check_scaffold_boundary_yamls_valid(project: Path, report: DoctorReport) -> None:
    """scaffold.boundary_yamls_valid — every templates/<stack>/scaffold-boundary.yaml parses + has required keys."""
    templates_dir = project / "src" / "templates"
    if not templates_dir.is_dir():
        report.checks.append(
            CheckResult(
                "scaffold.boundary_yamls_valid",
                SEV_PASS,
                "no templates/ dir (skip)",
            )
        )
        return

    boundary_problems: list[dict[str, Any]] = []
    boundary_count = 0
    for boundary_path in sorted(templates_dir.glob("*/scaffold-boundary.yaml")):
        boundary_count += 1
        stack_id = boundary_path.parent.name
        try:
            boundary_data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            boundary_problems.append({"stack": stack_id, "error": f"yaml parse: {exc}"})
            continue
        if not isinstance(boundary_data, dict):
            boundary_problems.append({"stack": stack_id, "error": "not a mapping"})
            continue
        for required_key in REQUIRED_BOUNDARY_KEYS:
            if required_key not in boundary_data:
                boundary_problems.append(
                    {
                        "stack": stack_id,
                        "error": f"missing key {required_key!r}",
                    }
                )
        declared_stack_id = boundary_data.get("stack")
        if declared_stack_id and declared_stack_id != stack_id:
            boundary_problems.append(
                {
                    "stack": stack_id,
                    "error": f"declared stack {declared_stack_id!r} != dir name {stack_id!r}",
                }
            )

    if boundary_problems:
        report.checks.append(
            CheckResult(
                "scaffold.boundary_yamls_valid",
                SEV_FAIL,
                f"{len(boundary_problems)} boundary problem(s) across {boundary_count} stack(s)",
                {"problems": boundary_problems},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "scaffold.boundary_yamls_valid",
                SEV_PASS,
                f"all {boundary_count} scaffold-boundary.yaml valid",
            )
        )
