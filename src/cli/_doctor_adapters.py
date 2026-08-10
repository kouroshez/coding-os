"""Doctor checks for the installed adapters: descriptors, symlinks, hook wiring.

Everything that can drift between `src/adapters/<id>/` and the `.claude/` or
`.codex/` directory it rendered into.
"""

from __future__ import annotations

import json
import logging
import shlex
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
