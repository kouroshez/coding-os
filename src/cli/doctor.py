"""`cos doctor` — deep health check for an initialized coding-os project.

Checks (fail-fast ordering):

    config.file_present  .coding-os.yaml exists and parses
    state.directory_present  state dir exists
    database.openable  coding-os.db opens
    database.schema_current  schema_version == 6
    database.tables_present  core tables present
    scaffold.roots_present  scaffold roots exist (AGENTS.md, Makefile, docs/)
    adapter.configured  adapter-specific (Claude settings.json + hook executability, or
        Codex hooks.json)
    scaffold.placeholders_resolved  no unresolved {{placeholder}} in scaffold text files
    scheduled.cron_configured nightly cron: plist installed, loaded, no failures, recent run

scaffold.manifest_fresh (manifest hash diff) and mcp.self_test_passes (MCP self-test) are wired in Phase 2.

Severity semantics (plan D9):
    PASS  — expected state
    WARN  — drift / extras / minor inconsistencies (exit 0)
    FAIL  — missing critical file / broken invariant (exit 1)
    --strict promotes WARN to exit 1.
"""

from ._doctor_run import run_doctor as run_doctor
from ._doctor_shared import (
    _DOCTOR_CFG,
    CODING_OS_ROOT,
    CONFIG_FILE,
    EXPECTED_SCHEMA_VERSION,
    EXPECTED_TABLES,
    IGNORED_PREFIXES,
    MANIFEST_PATH_DEFAULT,
    MCP_SERVER_PATH,
    PLACEHOLDER_MAX_BYTES,
    PLACEHOLDER_RE,
    PLACEHOLDER_SCAN_EXTENSIONS,
    PLACEHOLDER_SCAN_NAMES,
    PLACEHOLDER_SCAN_ROOTS,
    PLACEHOLDER_SCAN_SKIP,
    RUNTIME_PATHS,
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    STATE_DIR_DEFAULT,
    Any,
    CheckResult,
    DoctorReport,
    Path,
    _derive_expected_schema_version,
    _load_doctor_config,
    _load_runtime_paths,
    _scan_cfg,
    _scan_project_files,
    _schema_cfg,
    _tick,
    adapters_dir,
    asdict,
    click,
    contextlib,
    core_dir,
    current_core_version,
    data_root,
    dataclass,
    field,
    json,
    logger,
    logging,
    os,
    re,
    read_stamped_version,
    sqlite3,
    subprocess,
    sys,
    templates_dir,
    yaml,
)


def _format_text(report: DoctorReport, *, strict: bool) -> str:
    header = (
        f"Coding OS Doctor — {report.project_dir}\n"
        f"Agent: {report.agent or '?'}    Templates: {', '.join(report.templates) or 'none'}\n"
        + "="
        * 60
    )
    lines = [header]
    ordered_checks = sorted(report.checks, key=lambda c: (c.category, c.name))
    current_category: str | None = None
    for c in ordered_checks:
        if c.category != current_category:
            current_category = c.category
            lines.append("")
            lines.append(f"── {c.category} ──")
        badge = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[c.severity]
        lines.append(f"  {badge} {c.id:42s} {c.message}")
    lines.append("")
    s = report.summary()
    lines.append("-" * 60)
    exit_code = report.exit_code(strict=strict)
    status_icon = "✅" if exit_code == 0 else "❌"
    lines.append(
        f"{status_icon} Summary: {s['pass']} PASS, {s['warn']} WARN, {s['fail']} FAIL "
        f"(exit={exit_code})"
    )
    if report.suppressed:
        lines.append(
            f"   suppressed: {report.suppressed} check(s) via {', '.join(report.suppressed_globs)}"
        )
    return "\n".join(lines)


def _format_json(report: DoctorReport, *, strict: bool) -> str:
    payload = {
        "project_dir": report.project_dir,
        "agent": report.agent,
        "templates": report.templates,
        "checks": [{**asdict(c), "category": c.category, "name": c.name} for c in report.checks],
        "summary": {**report.summary(), "exit_code": report.exit_code(strict=strict)},
    }
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Split modules — cli.doctor stays the single public surface; checks live in
# doctor_checks_* siblings (imported last so they can import the kernel types).
# ---------------------------------------------------------------------------
from .doctor_checks_bootstrap import (  # noqa: E402
    _BOOTSTRAP_MIN_BASH_MAJOR,
    _BOOTSTRAP_MIN_PYTHON,
    _capture_tool_version,
    _check_bootstrap_bash,
    _check_bootstrap_git,
    _check_bootstrap_python,
    _check_bootstrap_sed,
    _check_bootstrap_uv,
    _probe_agent_sdk,
    _probe_otel,
    run_bootstrap_doctor,
)
from .doctor_checks_core import (  # noqa: E402
    _ANATOMY_TOP_LEVEL,
    _check_config,
    _check_core_version,
    _check_database,
    _check_scaffold_roots,
    _check_state_dir,
    _check_structure,
    _declared_src_segments,
)
from .doctor_checks_modules import (  # noqa: E402
    _check_hub_code_fresh,
    _check_module_command_drift,
    _check_module_consistency,
    _check_module_doc_drift,
    _check_module_rule_drift,
    _check_module_skill_drift,
    _check_runtime_errors,
    _check_subsystems_state_integrity,
)
from .doctor_checks_quality import _check_file_size_budget  # noqa: E402
from .doctor_checks_registry import (  # noqa: E402
    _check_agents_md_present,
    _check_category_balance,
    _check_mcp_actually_launches,
    _check_mcp_portable,
    _check_stack_registry_consistency,
    _check_stack_skills_linked,
    _load_coding_os_mcp_launch,
)
from .doctor_checks_runtime import (  # noqa: E402
    _check_cognition_registries,
    _check_hook_coverage,
    _check_presence_zombies,
    _check_scheduled,
)
from .doctor_checks_scaffold import (  # noqa: E402
    _check_adapter,
    _check_manifest,
    _check_mcp_selftest,
    _check_placeholders,
    _explain_check,
    _ignore_globs_from_config,
    _section_id,
    _suppress_checks,
)


@click.command()
@click.option("--project-dir", "-d", default=".", help="Project directory (default: cwd)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.option("--strict", is_flag=True, default=False, help="Promote WARN to exit 1")
@click.option("--manifest", default=None, help="Override manifest file path")
@click.option("--otel", is_flag=True, default=False, help="Probe OTEL exporter config and exit")
@click.option(
    "--bootstrap",
    is_flag=True,
    default=False,
    help="Preflight prerequisite checks (python/bash/git/uv/sed) — no project needed",
)
@click.option(
    "--agent-sdk",
    "--claude-sdk",
    "agent_sdk",
    is_flag=True,
    default=False,
    help="Print the active adapter SDK + CLI compatibility report and exit",
)
@click.option(
    "--ignore",
    "ignore_globs",
    multiple=True,
    help="Skip checks whose dotted ID matches this fnmatch glob (e.g. 'graph.*'). "
    "Repeatable. Merged with .coding-os.yaml::doctor.ignore.",
)
@click.option(
    "--explain",
    "explain_id",
    default=None,
    help="Print the docs/playbooks/doctor-checks.md section for the given check ID and exit.",
)
@click.option(
    "--tokens",
    "tokens",
    is_flag=True,
    default=False,
    help="Token-usage audit of agent transcripts (probe-and-exit, like --otel)",
)
@click.option(
    "--days",
    "tokens_days",
    type=int,
    default=7,
    help="Window for --tokens (default 7 days)",
)
@click.option(
    "--structure",
    "structure",
    is_flag=True,
    default=False,
    help="Validate the src/ tree against the declared project anatomy and exit",
)
def doctor(
    project_dir: str,
    output_format: str,
    strict: bool,
    manifest: str | None,
    otel: bool,
    bootstrap: bool,
    agent_sdk: bool,
    ignore_globs: tuple[str, ...],
    explain_id: str | None,
    tokens: bool,
    tokens_days: int,
    structure: bool,
) -> None:
    """Deep health check: scaffold, DB schema, adapter, manifest, MCP."""
    if tokens:
        from cli.doctor_tokens import (
            analyze_dispatch_cost,
            analyze_tokens,
            format_dispatch_cost_text,
            format_tokens_text,
        )

        proj = Path(project_dir).resolve()
        token_report = analyze_tokens(proj, days=tokens_days)
        cost_report = analyze_dispatch_cost(proj)
        if output_format == "json":
            click.echo(json.dumps({**token_report, "dispatch_cost": cost_report}, indent=2))
        else:
            click.echo(format_tokens_text(token_report))
            cost_text = format_dispatch_cost_text(cost_report)
            if cost_text:
                click.echo(cost_text)
        return
    if bootstrap:
        report = run_bootstrap_doctor()
        if output_format == "json":
            click.echo(_format_json(report, strict=strict))
        else:
            click.echo(_format_text(report, strict=strict))
        sys.exit(report.exit_code(strict=strict))
    if otel:
        _probe_otel()
        return
    if agent_sdk:
        _probe_agent_sdk()
        return
    if explain_id:
        click.echo(_explain_check(explain_id))
        return
    if structure:
        project = Path(project_dir).resolve()
        report = DoctorReport(project_dir=str(project), agent=None, templates=[])
        config_path = project / CONFIG_FILE
        config: dict[str, Any] | None = None
        if config_path.is_file():
            try:
                config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                config = None
        _check_structure(project, report, config)
        if output_format == "json":
            click.echo(_format_json(report, strict=strict))
        else:
            click.echo(_format_text(report, strict=strict))
        sys.exit(report.exit_code(strict=strict))
    project = Path(project_dir).resolve()
    manifest_path = Path(manifest).resolve() if manifest else None
    report = run_doctor(
        project,
        manifest_path=manifest_path,
        extra_ignores=list(ignore_globs) if ignore_globs else None,
    )
    if output_format == "json":
        click.echo(_format_json(report, strict=strict))
    else:
        click.echo(_format_text(report, strict=strict))
    sys.exit(report.exit_code(strict=strict))


__all__ = [
    "CODING_OS_ROOT",
    "CONFIG_FILE",
    "EXPECTED_SCHEMA_VERSION",
    "EXPECTED_TABLES",
    "IGNORED_PREFIXES",
    "MANIFEST_PATH_DEFAULT",
    "MCP_SERVER_PATH",
    "PLACEHOLDER_MAX_BYTES",
    "PLACEHOLDER_RE",
    "PLACEHOLDER_SCAN_EXTENSIONS",
    "PLACEHOLDER_SCAN_NAMES",
    "PLACEHOLDER_SCAN_ROOTS",
    "PLACEHOLDER_SCAN_SKIP",
    "RUNTIME_PATHS",
    "SEV_FAIL",
    "SEV_PASS",
    "SEV_WARN",
    "STATE_DIR_DEFAULT",
    "_ANATOMY_TOP_LEVEL",
    "_BOOTSTRAP_MIN_BASH_MAJOR",
    "_BOOTSTRAP_MIN_PYTHON",
    "_DOCTOR_CFG",
    "Any",
    "CheckResult",
    "DoctorReport",
    "Path",
    "_capture_tool_version",
    "_check_adapter",
    "_check_agents_md_present",
    "_check_bootstrap_bash",
    "_check_bootstrap_git",
    "_check_bootstrap_python",
    "_check_bootstrap_sed",
    "_check_bootstrap_uv",
    "_check_category_balance",
    "_check_cognition_registries",
    "_check_config",
    "_check_core_version",
    "_check_database",
    "_check_file_size_budget",
    "_check_hook_coverage",
    "_check_hub_code_fresh",
    "_check_manifest",
    "_check_mcp_actually_launches",
    "_check_mcp_portable",
    "_check_mcp_selftest",
    "_check_module_command_drift",
    "_check_module_consistency",
    "_check_module_doc_drift",
    "_check_module_rule_drift",
    "_check_module_skill_drift",
    "_check_placeholders",
    "_check_presence_zombies",
    "_check_runtime_errors",
    "_check_scaffold_roots",
    "_check_scheduled",
    "_check_stack_registry_consistency",
    "_check_stack_skills_linked",
    "_check_state_dir",
    "_check_structure",
    "_check_subsystems_state_integrity",
    "_declared_src_segments",
    "_derive_expected_schema_version",
    "_explain_check",
    "_format_json",
    "_format_text",
    "_ignore_globs_from_config",
    "_load_coding_os_mcp_launch",
    "_load_doctor_config",
    "_load_runtime_paths",
    "_probe_agent_sdk",
    "_probe_otel",
    "_scan_cfg",
    "_scan_project_files",
    "_schema_cfg",
    "_section_id",
    "_suppress_checks",
    "_tick",
    "adapters_dir",
    "asdict",
    "click",
    "contextlib",
    "core_dir",
    "current_core_version",
    "data_root",
    "dataclass",
    "doctor",
    "field",
    "json",
    "logger",
    "logging",
    "os",
    "re",
    "read_stamped_version",
    "run_bootstrap_doctor",
    "run_doctor",
    "sqlite3",
    "subprocess",
    "sys",
    "templates_dir",
    "yaml",
]
