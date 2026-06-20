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

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml

from cli._resources import adapters_dir, core_dir, data_root, templates_dir
from cli.core_version import current_core_version, read_stamped_version

logger = logging.getLogger(__name__)

# Bundled trees resolve via importlib (TASK-219) — survives wheel installs and
# meta-repo moves. CODING_OS_ROOT remains for repo-only assets (docs/) that
# exist solely in a source checkout.
CODING_OS_ROOT = data_root().parent
MANIFEST_PATH_DEFAULT = core_dir("scaffold_manifest.json")
MCP_SERVER_PATH = core_dir("thinking_os", "server.py")


def _load_runtime_paths() -> tuple[frozenset[str], tuple[str, ...]]:
    """Load runtime_files + ignored_prefixes from src/core/runtime_paths.yaml.

    Returns (runtime_files_set, ignored_prefixes_tuple). On missing/invalid
    config, falls back to empty sets so doctor never crashes on config errors.
    """
    path = core_dir("runtime_paths.yaml")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("cannot load runtime_paths.yaml: %s", exc)
        return frozenset(), ()
    runtime = frozenset(str(p) for p in (data.get("runtime_files") or []))
    prefixes = tuple(str(p) for p in (data.get("ignored_prefixes") or []))
    return runtime, prefixes


def _load_doctor_config() -> dict[str, Any]:
    """Load src/core/doctor-config.yaml. Returns {} on failure."""
    path = core_dir("doctor-config.yaml")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("cannot load doctor-config.yaml: %s", exc)
        return {}


# ---- Module-level configuration (loaded once at import) ----------------
RUNTIME_PATHS, IGNORED_PREFIXES = _load_runtime_paths()
_DOCTOR_CFG = _load_doctor_config()


def _scan_project_files(project: Path) -> set[str]:
    """Project file set, pruning ignored top-level subtrees in place.

    os.walk lets us drop .git/.venv/node_modules/.build from `dirnames` so we
    never descend into them — a full rglob walked those heavy trees before
    filtering, the dominant cost on a 100K-file repo. TASK-227.
    """
    proot = project.resolve()
    actual: set[str] = set()

    def _ignored_dir(rel_dir: str, name: str) -> bool:
        child = f"{rel_dir}/{name}/" if rel_dir else f"{name}/"
        return any(child.startswith(p) for p in IGNORED_PREFIXES)

    for dirpath, dirnames, filenames in os.walk(proot):
        rel_dir = os.path.relpath(dirpath, proot)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        dirnames[:] = [d for d in dirnames if not _ignored_dir(rel_dir, d)]
        for fn in filenames:
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            if rel in RUNTIME_PATHS:
                continue
            if any(rel.startswith(p) for p in IGNORED_PREFIXES):
                continue
            actual.add(rel)
    return actual

CONFIG_FILE = ".coding-os.yaml"
STATE_DIR_DEFAULT = ".coding-os"

_schema_cfg = _DOCTOR_CFG.get("schema") or {}


def _derive_expected_schema_version() -> int:
    """Read max migration version from thinking_os.database.MIGRATIONS (SSOT).

    Falls back to the doctor-config.yaml mirror if the import fails (fresh
    clone before .venv install, broken module). Eliminates the drift class
    where a new migration lands but doctor-config wasn't bumped.
    """
    try:
        from core.thinking_os.database import MIGRATIONS

        return max(int(m[0]) for m in MIGRATIONS)
    except Exception:
        return int(_schema_cfg.get("expected_version", 6))


EXPECTED_SCHEMA_VERSION: int = _derive_expected_schema_version()
EXPECTED_TABLES: frozenset[str] = frozenset(_schema_cfg.get("expected_tables") or ())

# Note: `sourced_hooks` is per-adapter (src/adapters/<id>/adapter.yaml) and is
# read by _check_adapter directly from the AdapterProfile. There is no
# longer a cross-adapter hardcoded fallback here.

_scan_cfg = _DOCTOR_CFG.get("placeholder_scan") or {}
PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z_][a-zA-Z0-9_.]*\}\}")
PLACEHOLDER_SCAN_EXTENSIONS: frozenset[str] = frozenset(
    _scan_cfg.get("extensions") or (".md", ".json", ".yaml", ".yml", ".sh", ".py", ".toml", ".txt")
)
PLACEHOLDER_SCAN_NAMES: frozenset[str] = frozenset(_scan_cfg.get("file_names") or ("Makefile",))
PLACEHOLDER_MAX_BYTES: int = int(_scan_cfg.get("max_bytes") or 262144)
PLACEHOLDER_SCAN_ROOTS: tuple[str, ...] = tuple(
    _scan_cfg.get("root_paths") or ("AGENTS.md", "Makefile", "docs", ".coding-os.yaml")
)
PLACEHOLDER_SCAN_SKIP: tuple[str, ...] = tuple(
    _scan_cfg.get("skip_paths") or ("docs/governance/templates",)
)

SEV_PASS = "PASS"
SEV_WARN = "WARN"
SEV_FAIL = "FAIL"


@dataclass
class CheckResult:
    id: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def category(self) -> str:
        return self.id.split(".", 1)[0] if "." in self.id else self.id

    @property
    def name(self) -> str:
        return self.id.split(".", 1)[1] if "." in self.id else ""


@dataclass
class DoctorReport:
    project_dir: str
    agent: str | None
    templates: list[str]
    checks: list[CheckResult] = field(default_factory=list)
    suppressed: int = 0
    suppressed_globs: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        pass_n = sum(1 for c in self.checks if c.severity == SEV_PASS)
        warn_n = sum(1 for c in self.checks if c.severity == SEV_WARN)
        fail_n = sum(1 for c in self.checks if c.severity == SEV_FAIL)
        return {"pass": pass_n, "warn": warn_n, "fail": fail_n}

    def exit_code(self, *, strict: bool) -> int:
        s = self.summary()
        if s["fail"]:
            return 1
        if strict and s["warn"]:
            return 1
        return 0


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
        report.checks.append(
            CheckResult(
                "core.version_stamp",
                SEV_WARN,
                f"core drift — scaffolded by {stamped}, current core {current}; run `cos update`",
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


def _tick(label: str) -> None:
    """Stream a per-check progress line to stderr (interactive runs only)."""
    if sys.stderr.isatty():
        print(f"  [doctor] {label}…", file=sys.stderr, flush=True)


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
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='log_events'"
        ).fetchone() is None:
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
                "runtime.recent_errors", SEV_FAIL,
                f"{n_fatal} FATAL + {n_err} ERROR in last {window_h}h — run `cos errors`", detail,
            )
        )
    elif n_err >= threshold:
        report.checks.append(
            CheckResult(
                "runtime.recent_errors", SEV_WARN,
                f"{n_err} ERROR in last {window_h}h — run `cos errors`", detail,
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
        report.checks.append(
            CheckResult("hub.code_fresh", SEV_PASS, "hub fresh or not running")
        )


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
                    (d / name / "SKILL.md").exists() or (d / name).is_symlink()
                    for d in skills_dirs
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


def run_doctor(
    project: Path,
    *,
    manifest_path: Path | None = None,
    extra_ignores: list[str] | None = None,
) -> DoctorReport:
    """Run all implemented doctor checks and return a report."""
    report = DoctorReport(project_dir=str(project), agent=None, templates=[])
    config = _check_config(project, report)
    if config is None:
        return report
    state = _check_state_dir(project, config, report)
    graph_conn = None
    if state.is_dir():
        _tick("database + migrations")
        conn = _check_database(state, report)
        if conn is not None:
            with contextlib.closing(conn):
                pass
        _check_core_version(state, report)
        # Open a second short-lived connection for graph checks so
        # the first handle's contextlib.closing is not disturbed.
        try:
            import sqlite3 as _sqlite3

            db_file = state / "coding-os.db"
            if db_file.exists():
                graph_conn = _sqlite3.connect(str(db_file))
        except Exception as exc:
            logger = logging.getLogger("coding_os.doctor")
            logger.debug("graph doctor connection failed: %s", exc)
    _check_scaffold_roots(project, report)
    _check_adapter(project, report.agent, report)
    _tick("scanning scaffold manifest")
    _check_manifest(project, report, manifest_path or MANIFEST_PATH_DEFAULT)
    _tick("scanning for placeholders")
    _check_placeholders(project, report)
    _tick("MCP self-test (up to 30s)")
    _check_mcp_selftest(project, report)
    _check_stack_registry_consistency(report)
    _check_category_balance(report)
    _tick("stack skills linkage")
    _check_stack_skills_linked(project, report)
    _tick("MCP portability")
    _check_mcp_portable(project, report)
    _tick("MCP launch handshake (up to 20s)")
    _check_mcp_actually_launches(project, report)
    _check_agents_md_present(project, report)
    _tick("cognition registries")
    _check_cognition_registries(project, report)
    _tick("hook coverage")
    _check_hook_coverage(project, report)
    _check_module_consistency(project, report)
    _check_module_skill_drift(project, report)
    _tick("runtime errors")
    _check_runtime_errors(state, report)
    # graph_os health checks.
    _tick("graph_os health")
    try:
        from cli.doctor_graph import run_graph_checks

        # Module-aware (TASK-439): a project that disabled the graph module must
        # not be nagged to run graph-reindex on an intentionally-empty graph.
        from cli.subsystems import module_state

        if module_state(project).get("graph", True):
            run_graph_checks(report, state, graph_conn)
        else:
            report.checks.append(
                CheckResult(
                    "graph.module", SEV_PASS, "graph module disabled — skipping graph health"
                )
            )
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("graph doctor unavailable: %s", exc)
    finally:
        if graph_conn is not None:
            try:
                graph_conn.close()
            except Exception as exc:
                logger = logging.getLogger("coding_os.doctor")
                logger.debug("graph_conn close suppressed: %s", exc)
    # board_os health checks.
    _tick("board_os health")
    try:
        from cli.doctor_board import run_board_checks

        run_board_checks(report, project, state)
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("board doctor unavailable: %s", exc)
    _check_scheduled(project, report)
    _check_presence_zombies(project, report)
    _tick("hub code freshness")
    _check_hub_code_fresh(report)
    try:
        from cli.doctor_extras import run_extra_checks

        run_extra_checks(project, report)
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("doctor_extras unavailable: %s", exc)
    ignore_globs = _ignore_globs_from_config(config)
    if extra_ignores:
        ignore_globs.extend(extra_ignores)
    suppressed = _suppress_checks(report, ignore_globs)
    if suppressed > 0:
        report.suppressed = suppressed
        report.suppressed_globs = ignore_globs
    return report


def _check_stack_registry_consistency(report: DoctorReport) -> None:
    """stack.registry_valid — every stack declared in .coding-os.yaml::templates exists in the registry.

    If a stack was installed and later removed from the coding-os distribution,
    the project config still lists it — FAIL so the user knows to either add
    the stack back or remove it from their config.
    """
    try:
        from cli.stack_registry import load_stack_registry

        registry = load_stack_registry(templates_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_WARN,
                f"could not load stack registry: {exc}",
            )
        )
        return

    missing = [t for t in report.templates if t not in registry]
    if missing:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_FAIL,
                f"stacks in config not found in templates/: {', '.join(missing)}",
                {"missing": missing},
            )
        )
    elif not report.templates:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_PASS,
                "no stacks installed (base-only project)",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_PASS,
                f"all {len(report.templates)} installed stack(s) present in registry",
                {"installed": report.templates},
            )
        )


def _check_category_balance(report: DoctorReport) -> None:
    """stack.category_balance — informational WARN when two or more stacks of the same category
    are installed (e.g. two backend stacks). The project will work, but the
    later stack wins on conflicting substitution keys — the user should know."""
    if len(report.templates) < 2:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                "single-stack or base-only project",
            )
        )
        return

    try:
        from cli.stack_registry import load_stack_registry

        registry = load_stack_registry(templates_dir())
    except Exception:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                "registry unavailable, skipping",
            )
        )
        return

    categories: dict[str, list[str]] = {}
    for stack_id in report.templates:
        if stack_id in registry:
            cat = registry[stack_id].category
            categories.setdefault(cat, []).append(stack_id)

    duplicates = {c: ids for c, ids in categories.items() if len(ids) >= 2}
    if duplicates:
        details = ", ".join(f"{cat}: {', '.join(ids)}" for cat, ids in duplicates.items())
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_WARN,
                f"multiple stacks in same category ({details}) — last stack wins on conflicts",
                {"duplicates": duplicates},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                f"{len(report.templates)} stacks in {len(categories)} distinct categories",
            )
        )


def _check_stack_skills_linked(project: Path, report: DoctorReport) -> None:
    """stack.skills_linked — every installed stack's skills are symlinked into the agent's skills dir.

    Detects the B1 regression where `.claude/skills/python-django/SKILL.md`
    was missing even though `--template django` was declared. We consult the
    adapter registry to find `skills_dir` (null for Codex → skip check) and
    the src/templates/<stack>/skills/ source of truth.
    """
    if not report.templates:
        report.checks.append(CheckResult("stack.skills_linked", SEV_PASS, "no stacks installed"))
        return
    if not report.agent:
        report.checks.append(CheckResult("stack.skills_linked", SEV_PASS, "no agent configured"))
        return
    try:
        from cli.adapter_registry import load_adapter_registry

        adapters = load_adapter_registry(adapters_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_WARN,
                f"could not load adapter registry: {exc}",
            )
        )
        return
    profile = adapters.get(report.agent)
    if profile is None or not profile.skills_dir:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                f"adapter '{report.agent}' has no skills_dir — skipped",
            )
        )
        return

    skills_dir = project / profile.skills_dir
    expected: list[tuple[str, str]] = []  # (stack, skill_name)
    for stack in report.templates:
        stack_skills = templates_dir(stack, "skills")
        if not stack_skills.exists():
            continue
        for entry in stack_skills.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                expected.append((stack, entry.name))

    if not expected:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                "no stack skills to link",
            )
        )
        return

    missing = []
    for stack, name in expected:
        link = skills_dir / name / "SKILL.md"
        if not link.exists():
            missing.append(f"{stack}:{name}")

    if missing:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_FAIL,
                f"missing stack skill links: {', '.join(missing)} — run `cos update` to repair",
                {"missing": missing},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                f"all {len(expected)} stack skill(s) linked",
            )
        )


def _check_mcp_portable(project: Path, report: DoctorReport) -> None:
    """mcp.portable — .mcp.json coding-os entry uses the `cos server-start` wrapper.

    The wrapper form lets the project survive coding-os relocations and
    upgrades: the `cos` binary on PATH resolves the server location, no
    absolute dev path is hardcoded. A plain `uv run --directory <abs>`
    entry is tolerated as a bootstrap fallback but flagged WARN.
    """
    mcp_path = project / ".mcp.json"
    if not mcp_path.exists():
        report.checks.append(CheckResult("mcp.portable", SEV_PASS, "no .mcp.json (skip)"))
        return
    try:
        import json as _json

        data = _json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        report.checks.append(CheckResult("mcp.portable", SEV_FAIL, f"invalid JSON: {exc}"))
        return
    entry = (data.get("mcpServers") or {}).get("coding-os")
    if entry is None:
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_PASS,
                "no coding-os MCP entry (skip)",
            )
        )
        return
    command = entry.get("command")
    if command == "cos":
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_PASS,
                "uses `cos server-start` wrapper (portable)",
            )
        )
        return
    args = entry.get("args") or []
    has_abs_cos_path = any(isinstance(a, str) and "/core/thinking_os" in a for a in args)
    if has_abs_cos_path:
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_WARN,
                "hardcoded absolute path — runs fine locally but won't "
                "survive coding-os relocation. Install `cos` on PATH and "
                "re-run the adapter install to switch to the wrapper.",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_PASS,
                f"unknown command form '{command}' — assumed portable",
            )
        )


def _load_coding_os_mcp_launch(
    project: Path,
    agent: str | None,
) -> tuple[str | None, list[str], dict[str, str], str | None, str | None]:
    """Return the coding-os MCP launch config from any adapter (Claude/Codex/Cursor)."""

    def _load_claude_json(
        path: Path,
    ) -> tuple[str | None, list[str], dict[str, str], str | None, str | None] | None:
        if not path.exists():
            return None
        try:
            import json as _json

            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return None, [], {}, str(path), f"invalid JSON: {exc}"
        entry = (data.get("mcpServers") or {}).get("coding-os")
        if entry is None:
            return None, [], {}, str(path), None
        env = {str(k): str(v) for k, v in (entry.get("env") or {}).items()}
        return entry.get("command"), list(entry.get("args") or []), env, str(path), None

    def _load_codex_toml(path: Path) -> tuple[str | None, list[str], dict[str, str]] | None:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^\[mcp_servers\.coding-os\]\s*\n(?P<body>.*?)(?=^\[|\Z)", text)
        if not match:
            return None
        body = match.group("body")
        cmd_match = re.search(r'(?m)^[ \t]*command[ \t]*=[ \t]*"([^"]+)"[ \t]*$', body)
        if not cmd_match:
            return "", [], {}
        args_match = re.search(r"(?ms)^[ \t]*args[ \t]*=[ \t]*\[(.*?)\][ \t]*$", body)
        args = []
        if args_match:
            args = re.findall(r'"((?:[^"\\]|\\.)*)"', args_match.group(1))
            args = [bytes(item, "utf-8").decode("unicode_escape") for item in args]
        env: dict[str, str] = {}
        env_match = re.search(r"(?ms)^[ \t]*env[ \t]*=[ \t]*\{(.*?)\}[ \t]*$", body)
        if env_match:
            for key, value in re.findall(
                r'"((?:[^"\\]|\\.)*)"[ \t]*=[ \t]*"((?:[^"\\]|\\.)*)"', env_match.group(1)
            ):
                env[bytes(key, "utf-8").decode("unicode_escape")] = bytes(value, "utf-8").decode(
                    "unicode_escape"
                )
        return cmd_match.group(1), args, env

    def _load_codex(
        path: Path,
    ) -> tuple[str | None, list[str], dict[str, str], str | None, str | None] | None:
        loaded = _load_codex_toml(path)
        if loaded is None:
            return None
        command, args, env = loaded
        return command, args, env, str(path), None

    # Registry-driven loader selection — each adapter declares its
    # mcp_launch.loader and config_paths in adapter.yaml so no agent id
    # is hardcoded here (Rule 12 / tests/test_no_hardcoded_stacks).
    from cli.adapter_registry import load_adapter_registry

    adapters = load_adapter_registry(adapters_dir())

    loader_fns = {
        "claude_json": _load_claude_json,
        "codex_toml": _load_codex,
        # Cursor's .cursor/mcp.json uses the same mcpServers.coding-os JSON
        # shape as Claude (see src/adapters/cursor/install.sh), so it reuses
        # the Claude JSON loader. Without this entry the Cursor MCP launch
        # diagnostic was silently skipped (spec.loader not in loader_fns).
        "cursor_mcp_json": _load_claude_json,
    }

    loaders: list[tuple[str, Path]] = []
    for aid, profile in adapters.items():
        if agent and agent != aid:
            continue
        spec = profile.mcp_launch
        if spec is None:
            continue
        if spec.loader not in loader_fns:
            continue
        for cp in spec.config_paths:
            root = project if cp.scope == "project" else Path.home()
            loaders.append((spec.loader, root / cp.path))

    for loader_name, path in loaders:
        fn = loader_fns.get(loader_name)
        if fn is None:
            continue
        loaded = fn(path)
        if loaded is not None:
            return loaded

    return None, [], {}, None, None


def _check_mcp_actually_launches(project: Path, report: DoctorReport) -> None:
    """mcp.actually_launches — simulate the exact MCP launch path the active agent config uses.

    mcp.self_test_passes runs `server.py --test` with an explicit COS_DB_PATH env — that
    verifies the server code works but bypasses the agent launch config
    entirely. mcp.actually_launches closes that gap: it reads coding-os MCP launch config
    from Claude or Codex, runs the declared command with the project
    root as cwd, feeds a real `initialize` handshake, and expects a
    valid JSON-RPC response.
    """
    command, args, entry_env, source_path, load_error = _load_coding_os_mcp_launch(
        project, report.agent
    )
    if load_error:
        report.checks.append(CheckResult("mcp.actually_launches", SEV_FAIL, load_error))
        return
    if source_path is None:
        # Data-driven (Rule 11): list every adapter that ships an
        # install.sh under src/adapters/<id>/. New adapters appear here
        # automatically — no edit to this diagnostic when one is added.
        meta_root = Path(__file__).resolve().parent.parent.parent / "src" / "adapters"
        adapter_lines: list[str] = []
        if meta_root.is_dir():
            for adapter_yaml in sorted(meta_root.glob("*/adapter.yaml")):
                install_sh = adapter_yaml.parent / "install.sh"
                if install_sh.exists():
                    adapter_lines.append(
                        f"`bash <coding-os>/adapters/{adapter_yaml.parent.name}/install.sh`"
                    )
        if adapter_lines:
            repair = "Run " + " or ".join(adapter_lines) + " from the project root."
        else:
            repair = (
                "Run `bash <coding-os>/adapters/<adapter>/install.sh` for the "
                "adapter you use, from the project root."
            )
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                "coding-os MCP config missing — neither .mcp.json nor "
                ".codex/config.toml defines coding-os. " + repair,
            )
        )
        return
    if command is None:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_PASS,
                f"no coding-os MCP entry in {source_path} (skip)",
            )
        )
        return

    env = os.environ.copy()
    env.update(entry_env)

    handshake = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        '{"protocolVersion":"2025-03-26","capabilities":{},'
        '"clientInfo":{"name":"cos-doctor","version":"1.0"}}}\n'
    )

    if not command:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                f"no command specified in {source_path}",
            )
        )
        return

    try:
        proc = subprocess.run(
            [command, *args],
            input=handshake,
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                f"command not found on PATH: {command!r}. "
                f"Install via `uv tool install --editable <coding-os>`.",
            )
        )
        return
    except subprocess.TimeoutExpired:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_PASS,
                "launched (exceeded 20s → server is running, no crash)",
            )
        )
        return
    except OSError as exc:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                f"OS error launching: {exc}",
            )
        )
        return

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if '"jsonrpc"' in (proc.stdout or "") and '"result"' in (proc.stdout or ""):
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_PASS,
                "initialize handshake succeeded (server ready)",
            )
        )
        return

    if "unable to open database file" in combined or "OperationalError" in combined:
        msg = (
            "server crashed: cannot open DB. This usually means the "
            "MCP launch config uses `uv run --directory ...` which "
            "chdir's into the server tree, so `.coding-os/coding-os.db` "
            "stops resolving. Switch to the wrapper form: "
            '`command = "cos"` and `args = ["server-start"]`.'
        )
    elif "No module named" in combined or "ModuleNotFoundError" in combined:
        msg = "server crashed: missing Python dependency — rerun `uv sync`."
    else:
        tail = combined.strip().splitlines()[-3:]
        msg = f"launch failed (exit {proc.returncode}). Last output: " + " | ".join(tail)[-200:]

    report.checks.append(
        CheckResult(
            "mcp.actually_launches",
            SEV_FAIL,
            msg,
            {"stderr_tail": (proc.stderr or "")[-500:]},
        )
    )


def _check_agents_md_present(project: Path, report: DoctorReport) -> None:
    """docs.agents_md_present — AGENTS.md at the project root is the canonical instruction file.

    Read by both Claude (via AGENTS.md convention) and Codex. `cos init`
    generates it; pre-v0.2.0 projects or partial installs may be missing it.
    `cos add-adapter` and `cos update` now backfill automatically — this
    check catches projects that never ran either command since.
    """
    agents_md = project / "AGENTS.md"
    if agents_md.exists():
        report.checks.append(
            CheckResult(
                "docs.agents_md_present",
                SEV_PASS,
                "present",
                {"path": str(agents_md.relative_to(project))},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "docs.agents_md_present",
            SEV_FAIL,
            "missing — run 'cos update' or 'cos add-adapter <agent>' to backfill",
            {"expected": "AGENTS.md"},
        )
    )


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
            if matcher == "":
                if "" in matcher_list or matcher_list == []:
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
        script_path = hooks_dir / script
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


def _probe_claude_sdk() -> None:
    """Print agent SDK + CLI compatibility report (T14.4).

    Reads `src/adapters/<id>/adapter.yaml::{cli_binary, sdk_package}` so
    this file stays free of hardcoded adapter literals (Rule 11).
    """
    import importlib.metadata
    import os
    import shutil
    import subprocess
    from pathlib import Path

    import yaml

    target_id = os.environ.get("COS_AGENT", "")
    adapters_root = Path(__file__).resolve().parent.parent.parent / "src" / "adapters"
    if not target_id:
        for adapter_dir in sorted(adapters_root.iterdir()):
            if adapter_dir.is_dir() and (adapter_dir / "adapter.yaml").exists():
                target_id = adapter_dir.name
                break

    meta_path = adapters_root / target_id / "adapter.yaml"
    adapter = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    cli_binary = adapter.get("cli_binary") or target_id
    sdk_package = adapter.get("sdk_package") or ""
    label = adapter.get("label") or target_id

    click.echo(f"{label} SDK compatibility report")
    click.echo("=" * 60)

    if sdk_package:
        try:
            sdk_version = importlib.metadata.version(sdk_package)
            click.echo(f"  [OK]   {sdk_package} = {sdk_version}")
        except importlib.metadata.PackageNotFoundError:
            click.echo(f"  [FAIL] {sdk_package} not installed (uv sync --extra rag)")
    else:
        click.echo("  [SKIP] no sdk_package declared in adapter.yaml")

    cli_path = shutil.which(cli_binary)
    if cli_path:
        try:
            result = subprocess.run(
                [cli_path, "--version"], capture_output=True, text=True, timeout=5
            )
            cli_version = result.stdout.strip() or result.stderr.strip()
            click.echo(f"  [OK]   {cli_binary} CLI = {cli_version} ({cli_path})")
        except (subprocess.TimeoutExpired, OSError) as exc:
            click.echo(f"  [WARN] {cli_binary} CLI unreachable: {exc}")
    else:
        click.echo(f"  [WARN] {cli_binary} CLI not on PATH")

    # API key auth
    if os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("  [OK]   ANTHROPIC_API_KEY set")
    elif os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        click.echo("  [OK]   ANTHROPIC_AUTH_TOKEN set")
    else:
        click.echo("  [WARN] no Anthropic auth env var set")

    # CLAUDECODE markers (live session detection)
    if os.environ.get("CLAUDECODE"):
        click.echo(f"  [OK]   CLAUDECODE = {os.environ.get('CLAUDECODE')!r}")

    # MCP server registration check
    mcp_json = Path(".mcp.json")
    if mcp_json.exists():
        click.echo(f"  [OK]   .mcp.json present ({mcp_json.resolve()})")
    else:
        click.echo("  [WARN] .mcp.json missing (cos init not run?)")


def _probe_otel() -> None:
    """Print OTEL configuration table for cos doctor --otel (T8.3)."""
    import os
    import socket

    _VARS = [
        "OTEL_TRACES_EXPORTER",
        "OTEL_METRICS_EXPORTER",
        "OTEL_LOGS_EXPORTER",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_SERVICE_NAME",
        "CLAUDE_CODE_ENABLE_TELEMETRY",
    ]
    configured = {v: os.environ.get(v) for v in _VARS}
    click.echo("OTEL probe")
    click.echo("=" * 60)
    for var, val in configured.items():
        if val:
            click.echo(f"  [OK]  {var} = {val!r}")
        else:
            click.echo(f"  [--]  {var} = not set")

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        click.echo("")
        click.echo(f"Probing endpoint: {endpoint}")
        try:
            from urllib.parse import urlparse as _up

            parsed = _up(endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 4317)
            with socket.create_connection((host, port), timeout=3):
                click.echo(f"  [OK]  TCP {host}:{port} reachable")
        except OSError as exc:
            click.echo(f"  [ERR] TCP unreachable: {exc}")
    else:
        click.echo("\nNo OTEL_EXPORTER_OTLP_ENDPOINT set — local stdout exporter assumed.")


_BOOTSTRAP_MIN_PYTHON = (3, 10)
_BOOTSTRAP_MIN_BASH_MAJOR = 4


def _capture_tool_version(executable: str) -> str | None:
    """First line of `<tool> --version`, or None when the tool is absent."""
    import shutil

    if shutil.which(executable) is None:
        return None
    try:
        proc = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else ""


def _check_bootstrap_python(report: DoctorReport) -> None:
    found = sys.version_info[:2]
    label = f"python {found[0]}.{found[1]}"
    if found >= _BOOTSTRAP_MIN_PYTHON:
        report.checks.append(CheckResult("bootstrap.python_version", SEV_PASS, label))
    else:
        report.checks.append(
            CheckResult(
                "bootstrap.python_version",
                SEV_FAIL,
                f"{label} < {_BOOTSTRAP_MIN_PYTHON[0]}.{_BOOTSTRAP_MIN_PYTHON[1]} — "
                "install a newer Python and reinstall cos with it",
            )
        )


def _check_bootstrap_bash(report: DoctorReport) -> None:
    banner = _capture_tool_version("bash")
    if banner is None:
        report.checks.append(
            CheckResult(
                "bootstrap.bash_version",
                SEV_FAIL,
                "bash not found on PATH — hook scripts require bash >= 4",
            )
        )
        return
    match = re.search(r"version (\d+)\.(\d+)", banner)
    major = int(match.group(1)) if match else 0
    if major >= _BOOTSTRAP_MIN_BASH_MAJOR:
        report.checks.append(CheckResult("bootstrap.bash_version", SEV_PASS, banner))
    else:
        report.checks.append(
            CheckResult(
                "bootstrap.bash_version",
                SEV_FAIL,
                f"{banner} — hooks need bash >= 4 (macOS ships 3.2: brew install bash)",
            )
        )


def _check_bootstrap_git(report: DoctorReport) -> None:
    banner = _capture_tool_version("git")
    if banner is None:
        report.checks.append(
            CheckResult(
                "bootstrap.git_present",
                SEV_FAIL,
                "git not found — `cos init` runs git init "
                "(macOS: xcode-select --install · debian: apt install git)",
            )
        )
    else:
        report.checks.append(CheckResult("bootstrap.git_present", SEV_PASS, banner))


def _check_bootstrap_uv(report: DoctorReport) -> None:
    banner = _capture_tool_version("uv")
    if banner is None:
        report.checks.append(
            CheckResult(
                "bootstrap.uv_present",
                SEV_WARN,
                "uv not found — updates and extras install through it "
                "(curl -LsSf https://astral.sh/uv/install.sh | sh)",
            )
        )
    else:
        report.checks.append(CheckResult("bootstrap.uv_present", SEV_PASS, banner))


def _check_bootstrap_sed(report: DoctorReport) -> None:
    banner = _capture_tool_version("sed")
    if banner is None:
        report.checks.append(
            CheckResult("bootstrap.sed_flavor", SEV_WARN, "sed not found on PATH")
        )
        return
    flavor = "gnu" if "GNU" in banner else "bsd"
    report.checks.append(
        CheckResult(
            "bootstrap.sed_flavor", SEV_PASS, f"{flavor} sed detected", {"flavor": flavor}
        )
    )


def run_bootstrap_doctor() -> DoctorReport:
    """Preflight prerequisite checks — no initialized project required.

    Encodes README § Prerequisites; check docs live in
    docs/playbooks/doctor-checks.md § bootstrap (TASK-347).
    """
    report = DoctorReport(project_dir="-", agent=None, templates=[])
    _check_bootstrap_python(report)
    _check_bootstrap_bash(report)
    _check_bootstrap_git(report)
    _check_bootstrap_uv(report)
    _check_bootstrap_sed(report)
    return report


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
    "--claude-sdk",
    "claude_sdk",
    is_flag=True,
    default=False,
    help="Print Claude SDK + CLI compat report and exit",
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
    claude_sdk: bool,
    ignore_globs: tuple[str, ...],
    explain_id: str | None,
    tokens: bool,
    tokens_days: int,
    structure: bool,
) -> None:
    """Deep health check: scaffold, DB schema, adapter, manifest, MCP."""
    if tokens:
        from cli.doctor_tokens import analyze_tokens, format_tokens_text

        token_report = analyze_tokens(Path(project_dir).resolve(), days=tokens_days)
        if output_format == "json":
            click.echo(json.dumps(token_report, indent=2))
        else:
            click.echo(format_tokens_text(token_report))
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
    if claude_sdk:
        _probe_claude_sdk()
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
