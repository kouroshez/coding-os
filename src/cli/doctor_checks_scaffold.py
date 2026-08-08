"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli._resources import adapters_dir

from ._doctor_shared import (  # noqa: F401
    _DOCTOR_CFG,
    CODING_OS_ROOT,
    CONFIG_FILE,
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
    CheckResult,
    DoctorReport,
    _derive_expected_schema_version,
    _load_doctor_config,
    _load_runtime_paths,
    _scan_project_files,
    _tick,
)

logger = logging.getLogger(__name__)


def _check_adapter(project: Path, agent: str | None, report: DoctorReport) -> None:
    """adapter.configured — adapter-specific files, driven entirely by src/adapters/<id>/adapter.yaml.

    Previously had hardcoded if/elif branches for claude + codex. Now we
    load the adapter profile and:
      - validate its declared settings_file is valid JSON
      - if it declares a hooks_dir, validate every .sh file is executable
        (skipping files listed in sourced_hooks)
    No new Python code is needed to support a new adapter — just add
    `src/adapters/<id>/adapter.yaml` and `install.sh`.
    """
    if agent is None:
        report.checks.append(CheckResult("adapter.configured", SEV_FAIL, "agent not set in config"))
        return

    try:
        # Late import to keep doctor usable even if adapter_registry has issues
        from cli.adapter_registry import load_adapter_registry

        adapters = load_adapter_registry(adapters_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "adapter.configured",
                SEV_WARN,
                f"could not load adapter registry: {exc}",
            )
        )
        return

    if agent not in adapters:
        report.checks.append(
            CheckResult(
                "adapter.configured",
                SEV_WARN,
                f"no adapter manifest for agent '{agent}'",
            )
        )
        return

    profile = adapters[agent]

    # 1. Validate declared settings file (if any) is parseable JSON.
    if profile.settings_file and profile.supports_settings_json:
        settings_path = project / profile.settings_file
        if not settings_path.exists():
            report.checks.append(
                CheckResult(
                    "adapter.configured",
                    SEV_FAIL,
                    f"{profile.settings_file} not found",
                    {"path": str(settings_path)},
                )
            )
            return
        try:
            json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.checks.append(
                CheckResult(
                    "adapter.configured",
                    SEV_FAIL,
                    f"{profile.settings_file} invalid JSON: {exc}",
                )
            )
            return

    # 2. Validate hooks dir (if declared): every .sh executable, except sourced ones.
    hook_count = 0
    if profile.hooks_dir:
        hooks_dir = project / profile.hooks_dir
        if not hooks_dir.is_dir():
            report.checks.append(
                CheckResult(
                    "adapter.configured",
                    SEV_FAIL,
                    f"{profile.hooks_dir} not found",
                )
            )
            return
        sourced = set(profile.sourced_hooks)
        hook_files = [h for h in sorted(hooks_dir.glob("*.sh")) if h.name not in sourced]
        broken_symlinks = [h.name for h in hook_files if h.is_symlink() and not h.exists()]
        if broken_symlinks:
            report.checks.append(
                CheckResult(
                    "adapter.configured",
                    SEV_FAIL,
                    f"broken hook symlinks: {', '.join(broken_symlinks[:5])}"
                    + (f" (+{len(broken_symlinks) - 5} more)" if len(broken_symlinks) > 5 else "")
                    + " — run: cos install",
                    {"broken_symlinks": broken_symlinks},
                )
            )
            return
        non_exec = [h.name for h in hook_files if not (h.stat().st_mode & 0o111)]
        if non_exec:
            report.checks.append(
                CheckResult(
                    "adapter.configured",
                    SEV_FAIL,
                    f"hooks not executable: {', '.join(non_exec)}",
                    {"non_executable": non_exec},
                )
            )
            return
        hook_count = len(hook_files)

    # 3. PASS
    if profile.hooks_dir:
        msg = f"{profile.settings_file or 'settings'} valid, {hook_count} hooks executable"
    else:
        msg = f"{profile.settings_file or 'manifest'} valid"
    report.checks.append(
        CheckResult(
            "adapter.configured",
            SEV_PASS,
            msg,
            {"hook_count": hook_count},
        )
    )


def _check_placeholders(project: Path, report: DoctorReport) -> None:
    """scaffold.placeholders_resolved — no unresolved {{placeholder}} in scaffold text files.

    Scan roots come from src/core/doctor-config.yaml::placeholder_scan.root_paths,
    plus every adapter's declared rules_dir, hooks_dir, and skills_dir (from
    the adapter registry) so Codex-style extras are discovered automatically.
    """
    offenders: list[dict[str, Any]] = []
    scan_roots = [project / root for root in PLACEHOLDER_SCAN_ROOTS]

    # Append adapter-declared directories so placeholders inside e.g.
    # .claude/rules/ or .codex/instructions/ are caught.
    try:
        from cli.adapter_registry import load_adapter_registry

        adapters = load_adapter_registry(adapters_dir())
    except Exception as exc:
        logger.debug("adapter registry skipped for placeholder scan: %s", exc)
        adapters = {}
    for profile in adapters.values():
        for attr in ("settings_file", "hooks_dir", "rules_dir", "skills_dir"):
            value = getattr(profile, attr)
            if value:
                candidate = project / value
                if candidate not in scan_roots:
                    scan_roots.append(candidate)

    for root in scan_roots:
        if not root.exists():
            continue
        targets = [root] if root.is_file() else list(root.rglob("*"))
        for f in targets:
            if not f.is_file():
                continue
            if f.suffix not in PLACEHOLDER_SCAN_EXTENSIONS and f.name not in PLACEHOLDER_SCAN_NAMES:
                continue
            try:
                rel_posix = f.relative_to(project).as_posix()
            except ValueError:
                rel_posix = ""
            if any(
                rel_posix == skip or rel_posix.startswith(skip + "/")
                for skip in PLACEHOLDER_SCAN_SKIP
            ):
                continue
            try:
                if f.stat().st_size > PLACEHOLDER_MAX_BYTES:
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Line-aware scan — skip sed-substitution rules (e.g.
            # `sed -e 's|{{X}}|...|g'`) which contain placeholders that
            # are pattern-side input to the rendering script itself, not
            # unresolved leftovers.
            matches: list[str] = []
            for line in text.splitlines():
                if "s|{{" in line or "s/{{" in line or "{{X}}" in line:
                    continue  # sed substitution rule — intentional placeholder
                matches.extend(PLACEHOLDER_RE.findall(line))
            if matches:
                offenders.append(
                    {"path": str(f.relative_to(project)), "placeholders": sorted(set(matches))}
                )

    if offenders:
        report.checks.append(
            CheckResult(
                "scaffold.placeholders_resolved",
                SEV_FAIL,
                f"{len(offenders)} file(s) contain unresolved placeholders",
                {"offenders": offenders[:20]},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "scaffold.placeholders_resolved",
                SEV_PASS,
                "no unresolved placeholders in scaffold files",
            )
        )


def _section_id(agent: str | None, templates: list[str]) -> str | None:
    """Map (agent, templates) to a manifest section id."""
    if agent is None:
        return None
    if not templates:
        return f"{agent}_base"
    if len(templates) == 1:
        return f"{agent}_{templates[0]}"
    return None  # multi-template not tracked


def _check_manifest(
    project: Path,
    report: DoctorReport,
    manifest_path: Path,
) -> None:
    """scaffold.manifest_fresh — compare project's file set against the section manifest.

    Missing expected paths → FAIL. Extras → WARN (user may have added files).
    """
    section_id = _section_id(report.agent, report.templates)
    if section_id is None:
        # Multi-stack projects have no precomputed section (manifest only
        # tracks single-stack combos). This is expected — file-by-file
        # validation for arbitrary combinations is out of scope for scaffold.manifest_fresh.
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_PASS,
                "multi-stack project — manifest diff not applicable",
                {"agent": report.agent, "templates": report.templates},
            )
        )
        return
    # Meta-repo detection — if this project IS the coding-os source tree
    # (src/cli/main.py + src/templates/_base/ both present), skip scaffold.manifest_fresh.
    # Meta-repo is the FACTORY, not a consumer of itself — comparing it
    # against a fresh `cos init -t meta` sandbox produces false missing.
    if (project / "src" / "cli" / "main.py").exists() and (
        project / "src" / "templates" / "_base"
    ).is_dir():
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_PASS,
                "meta-repo factory — manifest diff not applicable",
                {"agent": report.agent, "templates": report.templates},
            )
        )
        return
    if not manifest_path.exists():
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_WARN,
                f"manifest file not found at {manifest_path}",
            )
        )
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_WARN,
                f"manifest file invalid JSON: {exc}",
            )
        )
        return

    section = manifest.get("sections", {}).get(section_id)
    if not section:
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_WARN,
                f"manifest has no section '{section_id}'",
            )
        )
        return

    expected = set(section.get("paths", []))
    actual = _scan_project_files(project)

    missing = sorted(expected - actual)
    extras = sorted(actual - expected)

    if missing:
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_FAIL,
                f"{len(missing)} expected file(s) missing",
                {
                    "section": section_id,
                    "missing": missing[:20],
                    "missing_total": len(missing),
                },
            )
        )
    elif extras:
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_WARN,
                f"{len(extras)} extra file(s) not in manifest",
                {
                    "section": section_id,
                    "extras": extras[:20],
                    "extras_total": len(extras),
                },
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "scaffold.manifest_fresh",
                SEV_PASS,
                f"all {len(expected)} expected files present",
                {"section": section_id, "count": len(expected)},
            )
        )


def _check_mcp_selftest(project: Path, report: DoctorReport) -> None:
    """mcp.self_test_passes — run thinking_os MCP server self-test against the project DB."""
    if not MCP_SERVER_PATH.exists():
        report.checks.append(
            CheckResult(
                "mcp.self_test_passes",
                SEV_WARN,
                "MCP server.py not found in coding-os core",
            )
        )
        return
    db_path = project / ".coding-os" / "coding-os.db"
    env = os.environ.copy()
    env["COS_DB_PATH"] = str(db_path)
    try:
        proc = subprocess.run(
            [sys.executable, str(MCP_SERVER_PATH), "--test"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        report.checks.append(
            CheckResult("mcp.self_test_passes", SEV_FAIL, "self-test timed out (30s)")
        )
        return
    except OSError as exc:
        report.checks.append(CheckResult("mcp.self_test_passes", SEV_FAIL, f"cannot run: {exc}"))
        return
    if proc.returncode == 0:
        report.checks.append(CheckResult("mcp.self_test_passes", SEV_PASS, "self-test passed"))
    else:
        report.checks.append(
            CheckResult(
                "mcp.self_test_passes",
                SEV_FAIL,
                f"self-test exit {proc.returncode}",
                {"stderr": (proc.stderr or "")[-500:]},
            )
        )


def _ignore_globs_from_config(config: dict[str, Any]) -> list[str]:
    raw = (config.get("doctor") or {}).get("ignore") or []
    return [str(item) for item in raw if isinstance(item, (str, bytes))]


def _explain_check(check_id: str) -> str:
    doc_path = CODING_OS_ROOT / "docs" / "playbooks" / "doctor-checks.md"
    if not doc_path.exists():
        return f"doctor-checks reference not found at {doc_path}"
    text = doc_path.read_text(encoding="utf-8")
    marker = f"### {check_id}"
    start = text.find(marker)
    if start < 0:
        return (
            f"no entry for '{check_id}' in {doc_path.name}.\n"
            f"run `cos doctor --format json` to list every available ID."
        )
    end = text.find("\n### ", start + len(marker))
    if end < 0:
        end = text.find("\n---", start + len(marker))
    if end < 0:
        end = len(text)
    return text[start:end].rstrip() + f"\n\n— source: {doc_path}"


def _suppress_checks(report: DoctorReport, ignore_globs: list[str]) -> int:
    if not ignore_globs:
        return 0
    import fnmatch as _fnmatch

    before = len(report.checks)
    report.checks = [
        c for c in report.checks if not any(_fnmatch.fnmatch(c.id, pat) for pat in ignore_globs)
    ]
    return before - len(report.checks)
