"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor."""

from __future__ import annotations

import json
import logging
import os
import subprocess
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


def _check_cognition_registries(project: Path, report: DoctorReport) -> None:
    """cognition.registries_present — Cognition registries valid.

    - roles/F{1..11}_*.yaml all exist with id + activation + prompt_prefix
    - presets/registry.yaml parses and has ≥8 curated presets
    - situations/registry.yaml parses and has ≥6 situations
    - agents/F{1..11}_*.md all exist with valid YAML frontmatter
    """
    import re as _re

    thinking_os = project / "src" / "core" / "thinking_os"
    if not thinking_os.is_dir():
        report.checks.append(
            CheckResult("cognition.registries_present", SEV_PASS, "no thinking_os/ (skip)")
        )
        return

    issues: list[str] = []
    warnings: list[str] = []

    _EXPECTED_ROLES = [
        "researcher",
        "analyst",
        "architect",
        "documenter",
        "implementer",
        "reviewer",
        "debugger",
        "security_auditor",
        "deployer",
        "observer",
        "refactorer",
    ]

    # Role registry (primary, semantic names)
    roles_dir = thinking_os / "roles"
    if not roles_dir.is_dir():
        issues.append("roles/ directory missing")
    else:
        for role in _EXPECTED_ROLES:
            yaml_file = roles_dir / f"{role}.yaml"
            if not yaml_file.exists():
                issues.append(f"roles/{role}.yaml missing")
                continue
            try:
                import yaml as _yaml

                data = _yaml.safe_load(yaml_file.read_text()) or {}
                if data.get("id") != role:
                    issues.append(f"{yaml_file.name}: id mismatch (expected {role})")
                for required in (
                    "activation",
                    "prompt_prefix",
                    "criteria_required",
                    "intensity_steps",
                ):
                    if required not in data:
                        issues.append(f"{yaml_file.name}: missing '{required}'")
            except Exception as exc:
                issues.append(f"{yaml_file.name}: invalid YAML: {exc}")

    # Preset registry
    preset_reg = thinking_os / "presets" / "registry.yaml"
    if not preset_reg.exists():
        issues.append("presets/registry.yaml missing")
    else:
        try:
            import yaml as _yaml

            data = _yaml.safe_load(preset_reg.read_text()) or {}
            presets = data.get("presets", []) if isinstance(data, dict) else []
            count = len(presets) if isinstance(presets, list) else 0
            if count < 8:
                issues.append(f"presets/registry.yaml has {count} presets (need ≥8)")
            else:
                # Validate preset shape
                for preset in presets:
                    if "id" not in preset or "match" not in preset or "score" not in preset:
                        issues.append(f"preset malformed: {preset.get('id', '?')}")
                        break
        except Exception as exc:
            issues.append(f"presets/registry.yaml invalid YAML: {exc}")

    # Situation registry
    situation_reg = thinking_os / "situations" / "registry.yaml"
    if not situation_reg.exists():
        issues.append("situations/registry.yaml missing")
    else:
        try:
            import yaml as _yaml

            data = _yaml.safe_load(situation_reg.read_text()) or {}
            situations = data.get("situations", []) if isinstance(data, dict) else []
            count = len(situations) if isinstance(situations, list) else 0
            if count < 6:
                issues.append(f"situations/registry.yaml has {count} situations (need ≥6)")
        except Exception as exc:
            issues.append(f"situations/registry.yaml invalid YAML: {exc}")

    # Formula-agent files (semantic names — one file per role; reuses _EXPECTED_ROLES above)
    agents_dir = thinking_os / "agents"
    _ROLE_ID_RE = _re.compile(r"^id:\s*(\w+)", _re.MULTILINE)
    for role in _EXPECTED_ROLES:
        agent_file = agents_dir / f"{role}.md"
        if not agent_file.exists():
            issues.append(f"agents/{role}.md missing")
            continue
        content = agent_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            issues.append(f"{agent_file.name}: missing YAML frontmatter")
        else:
            m = _ROLE_ID_RE.search(content)
            if not m or m.group(1) != role:
                issues.append(f"{agent_file.name}: missing or wrong 'id: {role}' in frontmatter")

    if issues:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_FAIL,
                "; ".join(issues),
                {"issues": issues, "warnings": warnings},
            )
        )
    elif warnings:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_WARN,
                f"Roles/presets/situations OK (11 roles, 12+ presets, 6 situations, 11 agents); {'; '.join(warnings)}",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_PASS,
                "Cognition registries: 11 roles, 12+ presets, 6 situations, 11 formula-agents — all valid",
            )
        )


def _check_hook_coverage(project: Path, report: DoctorReport) -> None:
    """hook.coverage — every hook script in registry.yaml has an executable on disk
    AND each declared event/matcher pair is renderable for at least one
    adapter that lists the matching capability. Closes drift between
    registry.yaml (SSOT) and the rendered adapter templates.
    """
    registry_path = project / "src" / "core" / "hooks" / "registry.yaml"
    hooks_dir = project / "src" / "core" / "hooks"
    adapters_dir = project / "src" / "adapters"

    if not registry_path.exists() or not hooks_dir.is_dir():
        report.checks.append(
            CheckResult(
                "hook.coverage",
                SEV_PASS,
                "no registry.yaml (skip)",
            )
        )
        return

    try:
        import yaml as _yaml

        registry = _yaml.safe_load(registry_path.read_text()) or {}
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "hook.coverage",
                SEV_FAIL,
                f"registry.yaml invalid YAML: {exc}",
            )
        )
        return

    hooks = registry.get("hooks", []) if isinstance(registry, dict) else []
    if not isinstance(hooks, list) or not hooks:
        report.checks.append(
            CheckResult(
                "hook.coverage",
                SEV_FAIL,
                "registry.yaml has no hooks list",
            )
        )
        return

    adapter_caps: list[tuple[str, dict[str, list[str]]]] = []
    if adapters_dir.is_dir():
        try:
            import yaml as _yaml

            for adapter_yaml in sorted(adapters_dir.glob("*/adapter.yaml")):
                try:
                    data = _yaml.safe_load(adapter_yaml.read_text()) or {}
                except Exception:
                    continue
                raw = data.get("hook_capabilities") or data.get("capabilities") or {}
                normalized: dict[str, list[str]] = {}
                if isinstance(raw, dict):
                    for ev, spec in raw.items():
                        if isinstance(spec, dict):
                            matchers = spec.get("matchers") or spec.get("matcher") or [""]
                        else:
                            matchers = spec
                        if isinstance(matchers, str):
                            normalized[str(ev)] = [matchers]
                        elif isinstance(matchers, list):
                            normalized[str(ev)] = [str(m) for m in matchers]
                elif isinstance(raw, list):
                    for cap in raw:
                        if not isinstance(cap, dict):
                            continue
                        ev = str(cap.get("event") or "")
                        if not ev:
                            continue
                        matchers = cap.get("matchers") or cap.get("matcher") or [""]
                        if isinstance(matchers, str):
                            normalized.setdefault(ev, []).append(matchers)
                        elif isinstance(matchers, list):
                            normalized.setdefault(ev, []).extend(str(m) for m in matchers)
                if normalized:
                    adapter_caps.append((adapter_yaml.parent.name, normalized))
        except Exception as exc:
            logger = logging.getLogger("coding_os.doctor")
            logger.debug("adapter scan failed: %s", exc)

    def _pair_renderable(event: str, matcher: str) -> list[str]:
        out: list[str] = []
        for name, caps in adapter_caps:
            matcher_list = caps.get(event)
            if matcher_list is None:
                continue
            if matcher == "" and ("" in matcher_list or matcher_list == []):
                out.append(name)
                continue
            if matcher in matcher_list:
                out.append(name)
                continue
            wanted = set(matcher.split("|")) if matcher else set()
            for cand in matcher_list:
                if not cand:
                    continue
                cand_set = set(cand.split("|"))
                if wanted and wanted.issubset(cand_set):
                    out.append(name)
                    break
                if cand_set & wanted:
                    out.append(name)
                    break
        return out

    missing_scripts: list[str] = []
    non_executable: list[str] = []
    orphan_pairs: list[str] = []
    total_hooks = 0
    total_pairs = 0

    for entry in hooks:
        if not isinstance(entry, dict):
            continue
        total_hooks += 1
        hook_id = entry.get("id") or "?"
        script = entry.get("script") or f"{hook_id}.sh"
        # adapter_scope hooks live under src/adapters/<scope>/hooks/, not core —
        # resolve there so a claude-only hook isn't falsely flagged missing.
        scope = entry.get("adapter_scope")
        script_path = (
            (adapters_dir / str(scope) / "hooks" / script) if scope else (hooks_dir / script)
        )
        if not script_path.exists():
            missing_scripts.append(f"{hook_id}: {script}")
            continue
        if not os.access(script_path, os.X_OK):
            non_executable.append(f"{hook_id}: {script}")

        events = entry.get("events") or []
        if not isinstance(events, list):
            continue
        for ev in events:
            if not isinstance(ev, dict):
                continue
            total_pairs += 1
            event_name = str(ev.get("event") or "")
            matcher = str(ev.get("matcher") or "")
            if not event_name:
                orphan_pairs.append(f"{hook_id}: empty event")
                continue
            if adapter_caps and not _pair_renderable(event_name, matcher):
                orphan_pairs.append(f"{hook_id}: {event_name}/{matcher or '*'}")

    detail = {
        "total_hooks": total_hooks,
        "total_pairs": total_pairs,
        "adapters_scanned": [name for name, _ in adapter_caps],
        "missing_scripts": missing_scripts,
        "non_executable": non_executable,
        "orphan_pairs": orphan_pairs[:10],
    }

    if missing_scripts:
        report.checks.append(
            CheckResult(
                "hook.coverage",
                SEV_FAIL,
                f"{len(missing_scripts)} hook(s) missing script: " + "; ".join(missing_scripts[:5]),
                detail,
            )
        )
        return
    if non_executable:
        report.checks.append(
            CheckResult(
                "hook.coverage",
                SEV_WARN,
                f"{len(non_executable)} script(s) not executable: " + "; ".join(non_executable[:5]),
                detail,
            )
        )
        return
    if orphan_pairs and adapter_caps:
        report.checks.append(
            CheckResult(
                "hook.coverage",
                SEV_WARN,
                f"{len(orphan_pairs)} event/matcher pair(s) renderable for ZERO adapter — "
                f"may be intentional (e.g. SubagentStart Codex-incompatible). First: "
                + "; ".join(orphan_pairs[:5]),
                detail,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "hook.coverage",
            SEV_PASS,
            f"{total_hooks} hooks · {total_pairs} pairs · {len(adapter_caps)} adapter(s) scanned — all renderable",
            detail,
        )
    )


def _check_presence_zombies(project: Path, report: DoctorReport) -> None:
    """presence.no_zombies — flag presence files where ended_at is null AND PID is dead AND
    age >1h.  These are crashed sessions that the lazy GC could not reap
    on its own (Codex+Cursor lack Stop/SessionEnd matchers as of 2026-04).
    Warns at >20 zombies so the live-agents board can't accumulate noise.
    """
    import time as _time

    sessions_root = project / ".coding-os"
    if not sessions_root.is_dir():
        report.checks.append(
            CheckResult(
                "presence.no_zombies",
                SEV_PASS,
                "no .coding-os/ (skip)",
            )
        )
        return

    threshold = 3600
    now = int(_time.time())
    zombies: dict[str, int] = {}
    total_files = 0
    for agent_dir in sessions_root.iterdir():
        if not agent_dir.is_dir():
            continue
        sess_dir = agent_dir / "sessions"
        if not sess_dir.is_dir():
            continue
        count = 0
        for path in sess_dir.glob("*.json"):
            total_files += 1
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if now - mtime <= threshold:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                count += 1
                continue
            if data.get("ended_at") is not None:
                continue
            pid_raw = data.get("pid") or 0
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                pid = 0
            alive = False
            if pid > 0:
                try:
                    os.kill(pid, 0)
                    alive = True
                except ProcessLookupError:
                    alive = False
                except PermissionError:
                    alive = True
                except OSError:
                    alive = False
            if not alive:
                count += 1
        if count:
            zombies[agent_dir.name] = count

    detail = {
        "total_files": total_files,
        "zombies_per_agent": zombies,
        "threshold_secs": threshold,
    }
    total_zombies = sum(zombies.values())
    if total_zombies == 0:
        report.checks.append(
            CheckResult(
                "presence.no_zombies",
                SEV_PASS,
                f"0 zombies across {total_files} session file(s)",
                detail,
            )
        )
        return
    if total_zombies > 20:
        report.checks.append(
            CheckResult(
                "presence.no_zombies",
                SEV_WARN,
                f"{total_zombies} zombie session file(s) — run `cos hooks-list` "
                "or trigger any agent tool call to fire presence_gc.py",
                detail,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "presence.no_zombies",
            SEV_PASS,
            f"{total_zombies} zombie file(s) (<20 threshold) — GC will reap on next tick",
            detail,
        )
    )


def _check_scheduled(project: Path, report: DoctorReport) -> None:
    """scheduled.cron_configured — nightly cron: plist installed + loaded, no failures, run < 2d ago."""
    import datetime as _datetime
    import platform as _platform

    plist_dest = Path.home() / "Library" / "LaunchAgents" / "com.codingos.nightly.plist"
    last_run_path = project / ".coding-os" / "scheduled" / "last_run.json"
    is_macos = _platform.system() == "Darwin"
    plist_ok = True

    if is_macos:
        if not plist_dest.exists():
            report.checks.append(
                CheckResult(
                    "scheduled.cron_configured",
                    SEV_WARN,
                    "nightly cron not installed — run `cos cron install`",
                    {"plist": str(plist_dest)},
                )
            )
            return
        try:
            r = subprocess.run(
                ["launchctl", "list", "com.codingos.nightly"],
                capture_output=True,
                timeout=5,
            )
            if r.returncode != 0:
                report.checks.append(
                    CheckResult(
                        "scheduled.cron_configured",
                        SEV_WARN,
                        "plist present but not loaded — run `cos cron install`",
                        {"plist": str(plist_dest)},
                    )
                )
                return
        except OSError as exc:
            logger.debug("launchctl probe failed: %s", exc)
            plist_ok = False

    if not last_run_path.exists():
        prefix = "plist installed + loaded" if (is_macos and plist_ok) else "cron configured"
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_PASS,
                f"{prefix}, no run yet — run `cos cron run` to test",
            )
        )
        return

    try:
        data = json.loads(last_run_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_WARN,
                f"cannot read last_run.json: {exc}",
                {"path": str(last_run_path)},
            )
        )
        return

    disabled = data.get("disabled_reason")
    if disabled:
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_FAIL,
                f"auto-disabled: {disabled} — run `cos cron run --reset-failures`",
                {"disabled_reason": disabled, "last_error": data.get("last_error")},
            )
        )
        return

    failures = int(data.get("consecutive_failures") or 0)
    if failures >= 3:
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_FAIL,
                f"{failures} consecutive failures — run `cos cron run --reset-failures`",
                {"consecutive_failures": failures, "last_error": data.get("last_error")},
            )
        )
        return

    run_at = (data.get("run_at") or "")[:19]
    if run_at:
        try:
            run_dt = _datetime.datetime.fromisoformat(run_at).replace(tzinfo=_datetime.timezone.utc)
            now = _datetime.datetime.now(_datetime.timezone.utc)
            age_days = (now - run_dt).total_seconds() / 86400
            if age_days > 2:
                report.checks.append(
                    CheckResult(
                        "scheduled.cron_configured",
                        SEV_WARN,
                        f"last run {age_days:.1f}d ago — is launchd running?",
                        {"run_at": run_at, "age_days": round(age_days, 1)},
                    )
                )
                return
        except (ValueError, TypeError) as exc:
            logger.debug("run_at parse failed: %s", exc)

    parts: list[str] = []
    if is_macos and plist_ok:
        parts.append("plist loaded")
    if failures:
        parts.append(f"failures={failures}")
    if run_at:
        parts.append(f"last={run_at[:10]}")
    report.checks.append(
        CheckResult(
            "scheduled.cron_configured",
            SEV_PASS,
            ", ".join(parts) if parts else "healthy",
            {"consecutive_failures": failures, "run_at": run_at or None},
        )
    )
