"""doctor check: hook coverage — registry.yaml against scripts on disk and the
event/matcher pairs each adapter declares it can render.

Private sibling of cli.doctor; the check is re-exported by
`cli.doctor_checks_runtime`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ._doctor_shared import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
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

