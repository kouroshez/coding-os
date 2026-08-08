"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor."""

from __future__ import annotations

import logging
import os
from pathlib import Path

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

logger = logging.getLogger(__name__)


def _check_runtime_errors(state: Path, report: DoctorReport) -> None:
    """runtime.recent_errors — WARN/FAIL when the durable error store shows recent ERROR/FATAL."""
    db_file = state / "coding-os.db"
    if not db_file.exists():
        report.checks.append(
            CheckResult("runtime.recent_errors", SEV_PASS, "no durable error store yet")
        )
        return
    try:
        import sqlite3
        from datetime import datetime, timedelta, timezone

        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        if (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='log_events'"
            ).fetchone()
            is None
        ):
            report.checks.append(
                CheckResult("runtime.recent_errors", SEV_PASS, "log_events not present (pre-v32)")
            )
            conn.close()
            return
        window_h = int(os.environ.get("COS_DOCTOR_ERROR_WINDOW_HOURS", "24"))
        since = (datetime.now(timezone.utc) - timedelta(hours=window_h)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        try:
            from tools.logs import log_query
        except ImportError:
            from core.thinking_os.tools.logs import log_query
        n_err = log_query(conn, level="error", since=since, limit=1)["total"]
        n_fatal = log_query(conn, level="fatal", since=since, limit=1)["total"]
        conn.close()
    except Exception as exc:
        report.checks.append(
            CheckResult("runtime.recent_errors", SEV_WARN, f"could not read error store: {exc}")
        )
        return
    threshold = int(os.environ.get("COS_DOCTOR_ERROR_THRESHOLD", "1"))
    detail = {"errors": n_err, "fatal": n_fatal, "window_hours": window_h}
    if n_fatal > 0:
        report.checks.append(
            CheckResult(
                "runtime.recent_errors",
                SEV_FAIL,
                f"{n_fatal} FATAL + {n_err} ERROR in last {window_h}h — run `cos errors`",
                detail,
            )
        )
    elif n_err >= threshold:
        report.checks.append(
            CheckResult(
                "runtime.recent_errors",
                SEV_WARN,
                f"{n_err} ERROR in last {window_h}h — run `cos errors`",
                detail,
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "runtime.recent_errors", SEV_PASS, f"{n_err} errors in last {window_h}h", detail
            )
        )


def _check_hub_code_fresh(report: DoctorReport) -> None:
    """hub.code_fresh — WARN when a running Hub serves core code older than disk (run `cos hub restart`)."""
    try:
        from cli.hub_commands import _hub_code_is_stale
    except Exception as exc:
        logger.debug("hub staleness check unavailable: %s", exc)
        report.checks.append(
            CheckResult("hub.code_fresh", SEV_PASS, "hub staleness check unavailable (skip)")
        )
        return
    stale, newest = _hub_code_is_stale()
    if stale:
        changed = newest.name if newest else "core code"
        report.checks.append(
            CheckResult(
                "hub.code_fresh",
                SEV_WARN,
                f"Hub serving stale code — {changed} changed after it started; run `cos hub restart`",
                {"newest_changed": str(newest) if newest else None},
            )
        )
    else:
        report.checks.append(CheckResult("hub.code_fresh", SEV_PASS, "hub fresh or not running"))


def _check_module_consistency(project: Path, report: DoctorReport) -> None:
    """modules.state_consistency — .coding-os/disabled-hook-scripts matches subsystem state."""
    logger = logging.getLogger("coding_os.doctor")
    try:
        from cli.project_overrides import RUNTIME_ALLOWLIST, disabled_hook_scripts

        expected = disabled_hook_scripts(project)
        allowlist_file = project / ".coding-os" / RUNTIME_ALLOWLIST
        if not allowlist_file.exists():
            if expected:
                report.checks.append(
                    CheckResult(
                        "modules.state_consistency",
                        SEV_WARN,
                        f"{len(expected)} hook(s) should be disabled but "
                        ".coding-os/disabled-hook-scripts is missing — run `cos module disable <id>`",
                    )
                )
            else:
                report.checks.append(
                    CheckResult("modules.state_consistency", SEV_PASS, "no modules disabled")
                )
            return
        actual = {
            line.strip()
            for line in allowlist_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        # Bidirectional: `missing` = under-disabled (a hook that should be off is
        # absent); `extra` = over-disabled (the allowlist lists hooks for a module
        # that is ENABLED — the inverted half-state a failed-toggle rollback leaves
        # behind). Checking only `missing` reported SEV_PASS on the over-disabled
        # corruption, certifying a desynced project as healthy. (audit pass-4 #10)
        missing = expected - actual
        extra = actual - expected
        if missing or extra:
            parts: list[str] = []
            if missing:
                parts.append(
                    f"{len(missing)} expected hook(s) absent ({', '.join(sorted(missing)[:3])}…)"
                )
            if extra:
                parts.append(
                    f"{len(extra)} hook(s) disabled for ENABLED module(s) "
                    f"({', '.join(sorted(extra)[:3])}…) — over-disabled, likely a failed toggle rollback"
                )
            report.checks.append(
                CheckResult(
                    "modules.state_consistency",
                    SEV_WARN,
                    "disabled-hook-scripts drift: "
                    + "; ".join(parts)
                    + " — regenerate via `cos module enable/disable <id>`",
                )
            )
        else:
            report.checks.append(
                CheckResult(
                    "modules.state_consistency",
                    SEV_PASS,
                    f"allowlist matches module state ({len(expected)} disabled hook(s))",
                )
            )
    except Exception as exc:
        logger.debug("module consistency check skipped: %s", exc)


def _check_module_skill_drift(project: Path, report: DoctorReport) -> None:
    """modules.skill_drift — a disabled module's owned skill is still linked.

    The residue a `--keep-skills` disable (or an out-of-band edit) leaves: the
    module is off but its SKILL.md is still in an adapter skills dir. A skill
    also owned by an ENABLED module is never drift (ref-count)."""
    logger = logging.getLogger("coding_os.doctor")
    try:
        from cli.skill_commands import _installed_adapter_skills_dirs
        from cli.subsystems import load_subsystems, module_state

        modules = load_subsystems()
        state = module_state(project, modules)
        enabled_owned = {
            skill
            for mid, module in modules.items()
            if state.get(mid, True)
            for skill in module.skills
        }
        skills_dirs = _installed_adapter_skills_dirs(project)
        drift: list[str] = []
        for mid, module in modules.items():
            if state.get(mid, True):
                continue
            for name in module.skills:
                if name in enabled_owned:
                    continue
                if any(
                    (d / name / "SKILL.md").exists() or (d / name).is_symlink() for d in skills_dirs
                ):
                    drift.append(f"{name} (module '{mid}' off)")
        if drift:
            report.checks.append(
                CheckResult(
                    "modules.skill_drift",
                    SEV_WARN,
                    f"{len(drift)} skill(s) linked for disabled module(s): "
                    + ", ".join(sorted(set(drift))[:4])
                    + " — `cos skill disable <name>` or re-run `cos module disable <id>`",
                )
            )
        else:
            report.checks.append(
                CheckResult("modules.skill_drift", SEV_PASS, "no module/skill drift")
            )
    except Exception as exc:
        logger.debug("module skill drift check skipped: %s", exc)


def _check_module_command_drift(project: Path, report: DoctorReport) -> None:
    """modules.command_drift — a disabled module's owned slash-command is still
    linked in an adapter commands dir (TASK-481). A command also owned by an
    ENABLED module is never drift (ref-count)."""
    logger = logging.getLogger("coding_os.doctor")
    try:
        from cli.module_commands import _installed_adapter_commands_dirs
        from cli.subsystems import load_subsystems, module_state

        modules = load_subsystems()
        state = module_state(project, modules)
        enabled_owned = {
            cmd
            for mid, module in modules.items()
            if state.get(mid, True)
            for cmd in module.commands
        }
        command_dirs = _installed_adapter_commands_dirs(project)
        drift: list[str] = []
        for mid, module in modules.items():
            if state.get(mid, True):
                continue
            for name in module.commands:
                if name in enabled_owned:
                    continue
                cmd_file = f"{name}.md"
                if any(
                    (d / cmd_file).exists() or (d / cmd_file).is_symlink() for d in command_dirs
                ):
                    drift.append(f"{name} (module '{mid}' off)")
        if drift:
            report.checks.append(
                CheckResult(
                    "modules.command_drift",
                    SEV_WARN,
                    f"{len(drift)} command(s) linked for disabled module(s): "
                    + ", ".join(sorted(set(drift))[:4])
                    + " — re-run `cos module disable <id>`",
                )
            )
        else:
            report.checks.append(
                CheckResult("modules.command_drift", SEV_PASS, "no module/command drift")
            )
    except Exception as exc:
        logger.debug("module command drift check skipped: %s", exc)


def _check_module_rule_drift(project: Path, report: DoctorReport) -> None:
    """modules.rule_drift — a disabled module's owned core rule is still linked in
    an adapter rules dir (TASK-811). A rule also owned by an ENABLED module is
    never drift (ref-count)."""
    logger = logging.getLogger("coding_os.doctor")
    try:
        from cli.module_commands import _installed_adapter_rules_dirs
        from cli.subsystems import load_subsystems, module_state

        modules = load_subsystems()
        state = module_state(project, modules)
        enabled_owned = {
            rule for mid, module in modules.items() if state.get(mid, True) for rule in module.rules
        }
        rules_dirs = _installed_adapter_rules_dirs(project)
        drift: list[str] = []
        for mid, module in modules.items():
            if state.get(mid, True):
                continue
            for name in module.rules:
                if name in enabled_owned:
                    continue
                if any((d / name).exists() or (d / name).is_symlink() for d in rules_dirs):
                    drift.append(f"{name} (module '{mid}' off)")
        if drift:
            report.checks.append(
                CheckResult(
                    "modules.rule_drift",
                    SEV_WARN,
                    f"{len(drift)} rule(s) linked for disabled module(s): "
                    + ", ".join(sorted(set(drift))[:4])
                    + " — re-run `cos module disable <id>`",
                )
            )
        else:
            report.checks.append(
                CheckResult("modules.rule_drift", SEV_PASS, "no module/rule drift")
            )
    except Exception as exc:
        logger.debug("module rule drift check skipped: %s", exc)


def _check_module_doc_drift(project: Path, report: DoctorReport) -> None:
    """modules.doc_drift — a disabled module's `| module:X`-tagged scaffold doc is
    still present in the consumer (TASK-813 backstop). The consumer copy has its
    tag stripped at init, so we map via the tagged scaffold SOURCE, not the
    untagged destination."""
    logger = logging.getLogger("coding_os.doctor")
    try:
        import yaml as _yaml

        from cli.main import module_scaffold_doc_rels
        from cli.subsystems import load_subsystems, module_state

        modules = load_subsystems()
        state = module_state(project, modules)
        disabled = [mid for mid in modules if not state.get(mid, True)]
        if not disabled:
            report.checks.append(CheckResult("modules.doc_drift", SEV_PASS, "no module/doc drift"))
            return
        try:
            config = (
                _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8")) or {}
            )
            templates = tuple(config.get("templates") or [])
        except (OSError, _yaml.YAMLError):
            templates = ()
        drift: list[str] = []
        for mid in disabled:
            for rel in module_scaffold_doc_rels(templates, mid):
                if (project / rel).is_file():
                    drift.append(f"{rel} (module '{mid}' off)")
        if drift:
            report.checks.append(
                CheckResult(
                    "modules.doc_drift",
                    SEV_WARN,
                    f"{len(drift)} doc(s) present for disabled module(s): "
                    + ", ".join(sorted(set(drift))[:4])
                    + " — `cos module disable <id>` re-prunes (backed up), or remove them",
                )
            )
        else:
            report.checks.append(CheckResult("modules.doc_drift", SEV_PASS, "no module/doc drift"))
    except Exception as exc:
        logger.debug("module doc drift check skipped: %s", exc)


def _check_subsystems_state_integrity(project: Path, report: DoctorReport) -> None:
    """modules.state_integrity — a corrupt subsystems-state.json fails OPEN to
    all-enabled silently (TASK-474 P4-12); surface it as a WARN, not a false PASS."""
    logger = logging.getLogger("coding_os.doctor")
    try:
        from cli.subsystems import state_file_integrity

        reason = state_file_integrity(project)
        if reason:
            report.checks.append(
                CheckResult(
                    "modules.state_integrity",
                    SEV_WARN,
                    f"subsystems-state.json {reason} — module toggles silently fall back "
                    "to ALL-ENABLED; fix or delete the file",
                )
            )
        else:
            report.checks.append(
                CheckResult("modules.state_integrity", SEV_PASS, "subsystems-state.json readable")
            )
    except Exception as exc:
        logger.debug("subsystems state integrity check skipped: %s", exc)
