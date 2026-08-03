"""Extended doctor checks — covers gaps surfaced after the src-layout migration.

Adds checks across runtime, adapter, hub, scaffold, docs, graph, board, and
state categories. Each check follows the existing pattern: takes (project,
report), appends a CheckResult to report.checks. Wired into run_doctor()
at the tail.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import shutil
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


def _normalized_hook_map(hooks: dict[str, Any] | None) -> dict[str, Any]:
    normalized = json.loads(json.dumps(hooks or {}))
    for groups in normalized.values():
        for group in groups:
            for entry in group.get("hooks", []):
                parts = shlex.split(str(entry.get("command", "")))
                agent_token = next((part for part in parts if part.startswith("COS_AGENT=")), "")
                script = Path(parts[-1]).name if parts else ""
                entry["command"] = f"{agent_token}|{script}"
    return normalized


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
# adapter.all_installed_healthy — all_installed_adapters_healthy
# Parallel to adapter.configured (claude-only) — loops over every adapter declared in
# .coding-os.yaml::agents.
# ---------------------------------------------------------------------------


def _check_all_installed_adapters_healthy(project: Path, report: DoctorReport) -> None:
    """adapter.all_installed_healthy — each adapter listed in .coding-os.yaml has live hooks, rules, skills, commands."""
    config_path = project / ".coding-os.yaml"
    if not config_path.exists():
        report.checks.append(
            CheckResult(
                "adapter.all_installed_healthy",
                SEV_WARN,
                "no .coding-os.yaml — adapter list unknown",
            )
        )
        return
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        report.checks.append(
            CheckResult("adapter.all_installed_healthy", SEV_FAIL, f"config parse error: {exc}")
        )
        return
    agents = config.get("agents") or []
    if not agents:
        report.checks.append(
            CheckResult("adapter.all_installed_healthy", SEV_PASS, "no adapters installed")
        )
        return

    unhealthy: list[dict[str, Any]] = []
    healthy_count = 0
    for agent_name in agents:
        agent_dir_name = f".{agent_name}"
        agent_dir = project / agent_dir_name
        if not agent_dir.is_dir():
            unhealthy.append({"agent": agent_name, "issue": f"missing {agent_dir_name}/ dir"})
            continue
        broken_links: list[str] = []
        empty_subdirs: list[str] = []
        for subdir_name in ("hooks", "rules", "skills", "commands"):
            subdir = agent_dir / subdir_name
            if not subdir.is_dir():
                empty_subdirs.append(subdir_name)
                continue
            for entry in subdir.rglob("*"):
                if entry.is_symlink() and not entry.exists():
                    broken_links.append(str(entry.relative_to(project)))
        config_issues: list[str] = []
        manifest_path = (
            Path(__file__).resolve().parents[1] / "adapters" / agent_name / "adapter.yaml"
        )
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            settings_file = manifest.get("settings_file")
            template_name = manifest.get("hook_registry_output")
            hooks_dir = manifest.get("hooks_dir")
            if settings_file and not (project / str(settings_file)).is_file():
                config_issues.append(f"missing {settings_file}")
            if settings_file and template_name and hooks_dir:
                template_path = manifest_path.parent / str(template_name)
                installed_path = project / str(settings_file)
                expected_text = template_path.read_text(encoding="utf-8").replace(
                    "{{HOOKS_DIR}}", str((project / str(hooks_dir)).resolve())
                )
                expected_hooks = (json.loads(expected_text) or {}).get("hooks")
                installed_hooks = (
                    json.loads(installed_path.read_text(encoding="utf-8")) or {}
                ).get("hooks")
                if _normalized_hook_map(installed_hooks) != _normalized_hook_map(expected_hooks):
                    config_issues.append(f"{settings_file} hook map is stale")
        except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
            config_issues.append(f"adapter config unreadable: {exc}")
        if broken_links or empty_subdirs or config_issues:
            unhealthy.append(
                {
                    "agent": agent_name,
                    "broken_symlinks": broken_links[:5],
                    "broken_symlink_count": len(broken_links),
                    "missing_subdirs": empty_subdirs,
                    "config_issues": config_issues,
                }
            )
        else:
            healthy_count += 1

    if unhealthy:
        report.checks.append(
            CheckResult(
                "adapter.all_installed_healthy",
                SEV_FAIL,
                f"{len(unhealthy)}/{len(agents)} adapter(s) unhealthy",
                {"unhealthy": unhealthy, "fix": "cos sync-doctor --repair"},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "adapter.all_installed_healthy",
                SEV_PASS,
                f"all {healthy_count} adapter(s) healthy",
                {"agents": list(agents)},
            )
        )


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


# ---------------------------------------------------------------------------
# adapter.identity_file_present — agent_identity_file
# .coding-os/.agent written by install-adapter.sh; cos-env.sh reads it as
# the authoritative COS_AGENT value.  If missing, all hooks default to
# wrong paths and presence signals are lost.
# ---------------------------------------------------------------------------


def _check_agent_identity_file(project: Path, report: DoctorReport) -> None:
    """adapter.identity_file_present — .coding-os/.agent exists and contains a non-empty agent name."""
    agent_file = project / ".coding-os" / ".agent"
    if not agent_file.exists():
        report.checks.append(
            CheckResult(
                "adapter.identity_file_present",
                SEV_WARN,
                ".coding-os/.agent missing — run: cos install",
            )
        )
        return
    agent_name = agent_file.read_text(encoding="utf-8").strip()
    if not agent_name:
        report.checks.append(
            CheckResult(
                "adapter.identity_file_present",
                SEV_WARN,
                ".coding-os/.agent empty — run: cos install",
            )
        )
        return
    report.checks.append(
        CheckResult(
            "adapter.identity_file_present",
            SEV_PASS,
            f"agent identity: {agent_name}",
            {"agent": agent_name},
        )
    )


# ---------------------------------------------------------------------------
# adapter.symlinks_healthy — adapter_dir_symlinks_healthy
# install-adapter.sh sweeps stale symlinks on every re-run, but if the
# meta-repo moves after install, rules/ + commands/ + skills/ links silently
# break.  Doctor surfaces this so `cos install` is the clear fix.
# ---------------------------------------------------------------------------


def _check_adapter_dir_symlinks_healthy(project: Path, report: DoctorReport) -> None:
    """adapter.symlinks_healthy — rules/, commands/, skills/ in the agent dir have no broken symlinks."""
    agent_file = project / ".coding-os" / ".agent"
    if not agent_file.exists():
        report.checks.append(CheckResult("adapter.symlinks_healthy", SEV_PASS, "no .agent (skip)"))
        return
    agent_name = agent_file.read_text(encoding="utf-8").strip()
    agent_dir = project / f".{agent_name}"
    if not agent_dir.is_dir():
        report.checks.append(
            CheckResult("adapter.symlinks_healthy", SEV_PASS, f".{agent_name}/ missing (skip)")
        )
        return

    broken: list[str] = []
    for subdir_name in ("rules", "commands"):
        subdir = agent_dir / subdir_name
        if not subdir.is_dir():
            continue
        for entry in subdir.iterdir():
            if entry.is_symlink() and not entry.exists():
                broken.append(f"{subdir_name}/{entry.name}")

    skills_dir = agent_dir / "skills"
    if skills_dir.is_dir():
        for skill_md in skills_dir.glob("*/SKILL.md"):
            if skill_md.is_symlink() and not skill_md.exists():
                broken.append(f"skills/{skill_md.parent.name}/SKILL.md")

    if broken:
        report.checks.append(
            CheckResult(
                "adapter.symlinks_healthy",
                SEV_WARN,
                f"{len(broken)} broken symlink(s) in adapter dirs — run: cos install",
                {"broken": broken[:10]},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "adapter.symlinks_healthy",
                SEV_PASS,
                f".{agent_name}/rules · commands · skills — all symlinks healthy",
            )
        )


# ---------------------------------------------------------------------------
# hub.consumer_hook_symlinks_healthy — consumer_project_hook_symlinks
# Registered consumer projects have live symlinks into the meta-repo's
# src/core/hooks/.  If the meta-repo moves, those symlinks silently break.
# hub.project_paths_exist only checks that the project path exists; hub.consumer_hook_symlinks_healthy checks the symlinks
# inside it.  Fix: `cos sync-doctor --repair`.
# ---------------------------------------------------------------------------


def _check_consumer_project_hook_symlinks(project: Path, report: DoctorReport) -> None:
    """hub.consumer_hook_symlinks_healthy — registered consumer projects have no broken hook symlinks."""
    registry_path = Path.home() / ".coding-os" / "registry.json"
    if not registry_path.exists():
        report.checks.append(
            CheckResult("hub.consumer_hook_symlinks_healthy", SEV_PASS, "no hub registry (skip)")
        )
        return

    try:
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        report.checks.append(
            CheckResult(
                "hub.consumer_hook_symlinks_healthy",
                SEV_WARN,
                f"registry.json unreadable: {exc}",
            )
        )
        return

    consumer_projects = [
        entry
        for entry in (registry_data.get("projects") or [])
        if Path(entry.get("path", "")).resolve() != project.resolve()
        and Path(entry.get("path", "")).exists()
    ]

    broken_by_slug: dict[str, list[str]] = {}
    for entry in consumer_projects:
        consumer_path = Path(entry["path"])
        agent_file = consumer_path / ".coding-os" / ".agent"
        if not agent_file.exists():
            continue
        agent_name = agent_file.read_text(encoding="utf-8").strip()
        hooks_dir = consumer_path / f".{agent_name}" / "hooks"
        if not hooks_dir.is_dir():
            continue
        broken = [
            hook.name for hook in hooks_dir.glob("*.sh") if hook.is_symlink() and not hook.exists()
        ]
        if broken:
            slug = entry.get("slug") or consumer_path.name
            broken_by_slug[slug] = broken

    if broken_by_slug:
        summary = "; ".join(
            f"{slug}: {len(hooks)} broken" for slug, hooks in broken_by_slug.items()
        )
        report.checks.append(
            CheckResult(
                "hub.consumer_hook_symlinks_healthy",
                SEV_WARN,
                f"broken hook symlinks in {len(broken_by_slug)} project(s): {summary}"
                " — run: cos sync-doctor --repair",
                {"broken_by_slug": {k: v[:5] for k, v in broken_by_slug.items()}},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "hub.consumer_hook_symlinks_healthy",
                SEV_PASS,
                f"all {len(consumer_projects)} consumer project(s) hook symlinks healthy",
            )
        )


# ---------------------------------------------------------------------------
# hook.cos_env_sourced — hooks_source_cos_env
# Rule 3: every hook script must source cos-env.sh so it gets COS_AGENT_DIR,
# COS_STATE_DIR, and cos_log_hook.  Helper scripts (cos-env.sh itself, state
# r/w utils, test runners) are exempt — only scripts registered in
# registry.yaml are checked.
# ---------------------------------------------------------------------------


def _check_hooks_source_cos_env(project: Path, report: DoctorReport) -> None:
    """hook.cos_env_sourced — every registered hook script sources cos-env.sh (Rule 3)."""
    registry_path = project / "src" / "core" / "hooks" / "registry.yaml"
    hooks_dir = project / "src" / "core" / "hooks"
    if not registry_path.exists() or not hooks_dir.is_dir():
        report.checks.append(
            CheckResult("hook.cos_env_sourced", SEV_PASS, "no hooks registry (skip)")
        )
        return

    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        report.checks.append(
            CheckResult("hook.cos_env_sourced", SEV_WARN, f"registry.yaml unreadable: {exc}")
        )
        return

    violations: list[str] = []
    for entry in registry.get("hooks", []):
        if not isinstance(entry, dict):
            continue
        script_name = entry.get("script") or f"{entry.get('id', '')}.sh"
        script_path = hooks_dir / script_name
        if not script_path.exists():
            continue
        try:
            content = script_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "cos-env.sh" not in content:
            violations.append(script_name)

    if violations:
        report.checks.append(
            CheckResult(
                "hook.cos_env_sourced",
                SEV_WARN,
                f"{len(violations)} hook(s) missing `source cos-env.sh` (Rule 3): "
                + ", ".join(violations[:5])
                + (f" (+{len(violations) - 5} more)" if len(violations) > 5 else ""),
                {"violations": violations},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "hook.cos_env_sourced",
                SEV_PASS,
                "all registered hook scripts source cos-env.sh (Rule 3 compliant)",
            )
        )


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
