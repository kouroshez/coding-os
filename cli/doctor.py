"""`cos doctor` — deep health check for an initialized coding-os project.

Checks (fail-fast ordering):

    C1  .coding-os.yaml exists and parses
    C2  state dir exists
    C3  thinking-os.db opens
    C4  schema_version == 6
    C5  core tables present
    C6  scaffold roots exist (AGENTS.md, Makefile, docs/)
    C7  adapter-specific (Claude settings.json + hook executability, or
        Codex hooks.json)
    C9  no unresolved {{placeholder}} in scaffold text files

C8 (manifest hash diff) and C10 (MCP self-test) are wired in Phase 2.

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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import click
import yaml

logger = logging.getLogger(__name__)

CODING_OS_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH_DEFAULT = CODING_OS_ROOT / "core" / "scaffold_manifest.json"
MCP_SERVER_PATH = CODING_OS_ROOT / "core" / "thinking-os" / "server.py"


def _load_runtime_paths() -> tuple[frozenset[str], tuple[str, ...]]:
    """Load runtime_files + ignored_prefixes from core/runtime_paths.yaml.

    Returns (runtime_files_set, ignored_prefixes_tuple). On missing/invalid
    config, falls back to empty sets so doctor never crashes on config errors.
    """
    path = CODING_OS_ROOT / "core" / "runtime_paths.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("cannot load runtime_paths.yaml: %s", exc)
        return frozenset(), ()
    runtime = frozenset(str(p) for p in (data.get("runtime_files") or []))
    prefixes = tuple(str(p) for p in (data.get("ignored_prefixes") or []))
    return runtime, prefixes


def _load_doctor_config() -> dict[str, Any]:
    """Load core/doctor-config.yaml. Returns {} on failure."""
    path = CODING_OS_ROOT / "core" / "doctor-config.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("cannot load doctor-config.yaml: %s", exc)
        return {}


# ---- Module-level configuration (loaded once at import) ----------------
RUNTIME_PATHS, IGNORED_PREFIXES = _load_runtime_paths()
_DOCTOR_CFG = _load_doctor_config()

CONFIG_FILE = ".coding-os.yaml"
STATE_DIR_DEFAULT = ".coding-os"

_schema_cfg = _DOCTOR_CFG.get("schema") or {}
EXPECTED_SCHEMA_VERSION: int = int(_schema_cfg.get("expected_version", 6))
EXPECTED_TABLES: frozenset[str] = frozenset(
    _schema_cfg.get("expected_tables") or ()
)

# Note: `sourced_hooks` is per-adapter (adapters/<id>/adapter.yaml) and is
# read by _check_adapter directly from the AdapterProfile. There is no
# longer a cross-adapter hardcoded fallback here.

_scan_cfg = _DOCTOR_CFG.get("placeholder_scan") or {}
PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z_][a-zA-Z0-9_.]*\}\}")
PLACEHOLDER_SCAN_EXTENSIONS: frozenset[str] = frozenset(
    _scan_cfg.get("extensions") or (".md", ".json", ".yaml", ".yml", ".sh", ".py", ".toml", ".txt")
)
PLACEHOLDER_SCAN_NAMES: frozenset[str] = frozenset(
    _scan_cfg.get("file_names") or ("Makefile",)
)
PLACEHOLDER_MAX_BYTES: int = int(_scan_cfg.get("max_bytes") or 262144)
PLACEHOLDER_SCAN_ROOTS: tuple[str, ...] = tuple(
    _scan_cfg.get("root_paths") or ("AGENTS.md", "Makefile", "docs", ".coding-os.yaml")
)

SEV_PASS = "PASS"
SEV_WARN = "WARN"
SEV_FAIL = "FAIL"


@dataclass
class CheckResult:
    id: str
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoctorReport:
    project_dir: str
    agent: str | None
    templates: list[str]
    checks: list[CheckResult] = field(default_factory=list)

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
    """C1 — .coding-os.yaml exists and parses. Fatal if missing."""
    config_path = project / CONFIG_FILE
    if not config_path.exists():
        report.checks.append(
            CheckResult(
                "C1",
                "config_file",
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
                "C1",
                "config_file",
                SEV_FAIL,
                f"{CONFIG_FILE} is not valid YAML: {exc}",
                {"path": str(config_path)},
            )
        )
        return None
    report.checks.append(
        CheckResult("C1", "config_file", SEV_PASS, "valid", {"keys": sorted(data.keys())})
    )
    report.agent = (data.get("agents") or [None])[0]
    report.templates = list(data.get("templates") or [])
    return data


def _check_state_dir(project: Path, config: dict[str, Any], report: DoctorReport) -> Path:
    """C2 — state dir exists."""
    state = project / config.get("state_dir", STATE_DIR_DEFAULT)
    if not state.is_dir():
        report.checks.append(
            CheckResult(
                "C2", "state_dir", SEV_FAIL, "state directory missing",
                {"path": str(state)},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C2", "state_dir", SEV_PASS, "present",
                {"path": str(state)},
            )
        )
    return state


def _check_database(state: Path, report: DoctorReport) -> sqlite3.Connection | None:
    """C3 + C4 + C5 — DB opens, schema version 6, all 11 tables present."""
    db_path = state / "thinking-os.db"
    if not db_path.exists():
        report.checks.append(
            CheckResult(
                "C3", "database_open", SEV_FAIL, "thinking-os.db not found",
                {"path": str(db_path)},
            )
        )
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "C3", "database_open", SEV_FAIL, f"cannot open DB: {exc}",
                {"path": str(db_path)},
            )
        )
        return None
    report.checks.append(
        CheckResult("C3", "database_open", SEV_PASS, "opened", {"path": str(db_path)})
    )

    try:
        cur = conn.execute("SELECT MAX(version) FROM schema_version")
        row = cur.fetchone()
        version = int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "C4", "schema_version", SEV_FAIL,
                f"schema_version query failed: {exc}",
            )
        )
        version = None

    if version is None:
        pass  # already reported
    elif version < EXPECTED_SCHEMA_VERSION:
        report.checks.append(
            CheckResult(
                "C4", "schema_version", SEV_FAIL,
                f"schema version {version} < expected {EXPECTED_SCHEMA_VERSION}",
                {"actual": version, "expected": EXPECTED_SCHEMA_VERSION},
            )
        )
    elif version > EXPECTED_SCHEMA_VERSION:
        report.checks.append(
            CheckResult(
                "C4", "schema_version", SEV_WARN,
                f"schema version {version} newer than expected {EXPECTED_SCHEMA_VERSION}",
                {"actual": version, "expected": EXPECTED_SCHEMA_VERSION},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C4", "schema_version", SEV_PASS, f"v{version}",
                {"actual": version},
            )
        )

    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual = {row[0] for row in cur.fetchall()}
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult("C5", "core_tables", SEV_FAIL, f"table list failed: {exc}")
        )
        return conn

    missing = sorted(EXPECTED_TABLES - actual)
    if missing:
        report.checks.append(
            CheckResult(
                "C5", "core_tables", SEV_FAIL,
                f"missing tables: {', '.join(missing)}",
                {"missing": missing, "found": sorted(actual)},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C5", "core_tables", SEV_PASS,
                f"all {len(EXPECTED_TABLES)} core tables present",
                {"count": len(actual)},
            )
        )
    return conn


def _check_scaffold_roots(project: Path, report: DoctorReport) -> None:
    """C6 — AGENTS.md, Makefile, docs/ exist at project root."""
    required = {
        "AGENTS.md": project / "AGENTS.md",
        "Makefile": project / "Makefile",
        "docs/": project / "docs",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        report.checks.append(
            CheckResult(
                "C6", "scaffold_roots", SEV_FAIL,
                f"missing: {', '.join(missing)}",
                {"missing": missing},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C6", "scaffold_roots", SEV_PASS,
                "AGENTS.md, Makefile, docs/ all present",
            )
        )


def _check_adapter(project: Path, agent: str | None, report: DoctorReport) -> None:
    """C7 — adapter-specific files, driven entirely by adapters/<id>/adapter.yaml.

    Previously had hardcoded if/elif branches for claude + codex. Now we
    load the adapter profile and:
      - validate its declared settings_file is valid JSON
      - if it declares a hooks_dir, validate every .sh file is executable
        (skipping files listed in sourced_hooks)
    No new Python code is needed to support a new adapter — just add
    `adapters/<id>/adapter.yaml` and `install.sh`.
    """
    if agent is None:
        report.checks.append(
            CheckResult("C7", "adapter", SEV_FAIL, "agent not set in config")
        )
        return

    try:
        # Late import to keep doctor usable even if adapter_registry has issues
        from cli.adapter_registry import load_adapter_registry
        adapters = load_adapter_registry(CODING_OS_ROOT / "adapters")
    except Exception as exc:  # noqa: BLE001 — registry errors shouldn't crash doctor
        report.checks.append(
            CheckResult(
                "C7", "adapter", SEV_WARN,
                f"could not load adapter registry: {exc}",
            )
        )
        return

    if agent not in adapters:
        report.checks.append(
            CheckResult(
                "C7", "adapter", SEV_WARN,
                f"no adapter manifest for agent '{agent}'",
            )
        )
        return

    profile = adapters[agent]
    check_name = f"{agent}_adapter"

    # 1. Validate declared settings file (if any) is parseable JSON.
    if profile.settings_file and profile.supports_settings_json:
        settings_path = project / profile.settings_file
        if not settings_path.exists():
            report.checks.append(
                CheckResult(
                    "C7", check_name, SEV_FAIL,
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
                    "C7", check_name, SEV_FAIL,
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
                    "C7", check_name, SEV_FAIL,
                    f"{profile.hooks_dir} not found",
                )
            )
            return
        sourced = set(profile.sourced_hooks)
        hook_files = [
            h for h in sorted(hooks_dir.glob("*.sh")) if h.name not in sourced
        ]
        non_exec = [h.name for h in hook_files if not (h.stat().st_mode & 0o111)]
        if non_exec:
            report.checks.append(
                CheckResult(
                    "C7", check_name, SEV_FAIL,
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
            "C7", check_name, SEV_PASS, msg,
            {"hook_count": hook_count},
        )
    )


def _check_placeholders(project: Path, report: DoctorReport) -> None:
    """C9 — no unresolved {{placeholder}} in scaffold text files.

    Scan roots come from core/doctor-config.yaml::placeholder_scan.root_paths,
    plus every adapter's declared rules_dir, hooks_dir, and skills_dir (from
    the adapter registry) so Codex-style extras are discovered automatically.
    """
    offenders: list[dict[str, Any]] = []
    scan_roots = [project / root for root in PLACEHOLDER_SCAN_ROOTS]

    # Append adapter-declared directories so placeholders inside e.g.
    # .claude/rules/ or .codex/instructions/ are caught.
    try:
        from cli.adapter_registry import load_adapter_registry
        adapters = load_adapter_registry(CODING_OS_ROOT / "adapters")
    except Exception as exc:  # noqa: BLE001
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
                if f.stat().st_size > PLACEHOLDER_MAX_BYTES:
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            matches = PLACEHOLDER_RE.findall(text)
            if matches:
                offenders.append(
                    {"path": str(f.relative_to(project)), "placeholders": sorted(set(matches))}
                )

    if offenders:
        report.checks.append(
            CheckResult(
                "C9", "placeholders_resolved", SEV_FAIL,
                f"{len(offenders)} file(s) contain unresolved placeholders",
                {"offenders": offenders[:20]},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C9", "placeholders_resolved", SEV_PASS,
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
    """C8 — compare project's file set against the section manifest.

    Missing expected paths → FAIL. Extras → WARN (user may have added files).
    """
    section_id = _section_id(report.agent, report.templates)
    if section_id is None:
        # Multi-stack projects have no precomputed section (manifest only
        # tracks single-stack combos). This is expected — file-by-file
        # validation for arbitrary combinations is out of scope for C8.
        report.checks.append(
            CheckResult(
                "C8", "manifest_diff", SEV_PASS,
                "multi-stack project — manifest diff not applicable",
                {"agent": report.agent, "templates": report.templates},
            )
        )
        return
    if not manifest_path.exists():
        report.checks.append(
            CheckResult(
                "C8", "manifest_diff", SEV_WARN,
                f"manifest file not found at {manifest_path}",
            )
        )
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.checks.append(
            CheckResult(
                "C8", "manifest_diff", SEV_WARN,
                f"manifest file invalid JSON: {exc}",
            )
        )
        return

    section = manifest.get("sections", {}).get(section_id)
    if not section:
        report.checks.append(
            CheckResult(
                "C8", "manifest_diff", SEV_WARN,
                f"manifest has no section '{section_id}'",
            )
        )
        return

    expected = set(section.get("paths", []))
    actual = set()
    for f in project.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(project).as_posix()
        if rel in RUNTIME_PATHS:
            continue
        if any(rel.startswith(p) for p in IGNORED_PREFIXES):
            continue
        actual.add(rel)

    missing = sorted(expected - actual)
    extras = sorted(actual - expected)

    if missing:
        report.checks.append(
            CheckResult(
                "C8", "manifest_diff", SEV_FAIL,
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
                "C8", "manifest_diff", SEV_WARN,
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
                "C8", "manifest_diff", SEV_PASS,
                f"all {len(expected)} expected files present",
                {"section": section_id, "count": len(expected)},
            )
        )


def _check_mcp_selftest(project: Path, report: DoctorReport) -> None:
    """C10 — run thinking-os MCP server self-test against the project DB."""
    if not MCP_SERVER_PATH.exists():
        report.checks.append(
            CheckResult(
                "C10", "mcp_selftest", SEV_WARN,
                "MCP server.py not found in coding-os core",
            )
        )
        return
    db_path = project / ".coding-os" / "thinking-os.db"
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
            CheckResult("C10", "mcp_selftest", SEV_FAIL, "self-test timed out (30s)")
        )
        return
    except OSError as exc:
        report.checks.append(
            CheckResult("C10", "mcp_selftest", SEV_FAIL, f"cannot run: {exc}")
        )
        return
    if proc.returncode == 0:
        report.checks.append(
            CheckResult("C10", "mcp_selftest", SEV_PASS, "self-test passed")
        )
    else:
        report.checks.append(
            CheckResult(
                "C10", "mcp_selftest", SEV_FAIL,
                f"self-test exit {proc.returncode}",
                {"stderr": (proc.stderr or "")[-500:]},
            )
        )


def run_doctor(project: Path, *, manifest_path: Path | None = None) -> DoctorReport:
    """Run all implemented doctor checks and return a report."""
    report = DoctorReport(
        project_dir=str(project), agent=None, templates=[]
    )
    config = _check_config(project, report)
    if config is None:
        return report
    state = _check_state_dir(project, config, report)
    graph_conn = None
    if state.is_dir():
        conn = _check_database(state, report)
        if conn is not None:
            with contextlib.closing(conn):
                pass
        # Open a second short-lived connection for Phase I graph checks so
        # the first handle's contextlib.closing is not disturbed.
        try:
            import sqlite3 as _sqlite3
            db_file = state / "thinking-os.db"
            if db_file.exists():
                graph_conn = _sqlite3.connect(str(db_file))
        except Exception as exc:  # noqa: BLE001 — doctor must not crash
            logger = logging.getLogger("coding_os.doctor")
            logger.debug("graph doctor connection failed: %s", exc)
    _check_scaffold_roots(project, report)
    _check_adapter(project, report.agent, report)
    _check_manifest(project, report, manifest_path or MANIFEST_PATH_DEFAULT)
    _check_placeholders(project, report)
    _check_mcp_selftest(project, report)
    _check_stack_registry_consistency(report)
    _check_category_balance(report)
    _check_stack_skills_linked(project, report)
    _check_mcp_portable(project, report)
    _check_mcp_actually_launches(project, report)
    _check_agents_md_present(project, report)
    # Phase I.14 — graph-os health (C16-C22).
    try:
        from cli.doctor_graph import run_graph_checks  # noqa: WPS433
        run_graph_checks(report, state, graph_conn)
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("graph doctor unavailable: %s", exc)
    finally:
        if graph_conn is not None:
            try:
                graph_conn.close()
            except Exception as exc:  # noqa: BLE001
                logger = logging.getLogger("coding_os.doctor")
                logger.debug("graph_conn close suppressed: %s", exc)
    # Phase L.9 — board-os health (C20-C23).
    try:
        from cli.doctor_board import run_board_checks  # noqa: WPS433
        run_board_checks(report, project, state)
    except ImportError as exc:
        logger = logging.getLogger("coding_os.doctor")
        logger.debug("board doctor unavailable: %s", exc)
    return report


def _check_stack_registry_consistency(report: DoctorReport) -> None:
    """C11 — every stack declared in .coding-os.yaml::templates exists in the registry.

    If a stack was installed and later removed from the coding-os distribution,
    the project config still lists it — FAIL so the user knows to either add
    the stack back or remove it from their config.
    """
    try:
        from cli.stack_registry import load_stack_registry
        registry = load_stack_registry(CODING_OS_ROOT / "templates")
    except Exception as exc:  # noqa: BLE001 — doctor must not crash
        report.checks.append(
            CheckResult(
                "C11", "stack_registry", SEV_WARN,
                f"could not load stack registry: {exc}",
            )
        )
        return

    missing = [t for t in report.templates if t not in registry]
    if missing:
        report.checks.append(
            CheckResult(
                "C11", "stack_registry", SEV_FAIL,
                f"stacks in config not found in templates/: {', '.join(missing)}",
                {"missing": missing},
            )
        )
    elif not report.templates:
        report.checks.append(
            CheckResult(
                "C11", "stack_registry", SEV_PASS,
                "no stacks installed (base-only project)",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C11", "stack_registry", SEV_PASS,
                f"all {len(report.templates)} installed stack(s) present in registry",
                {"installed": report.templates},
            )
        )


def _check_category_balance(report: DoctorReport) -> None:
    """C12 — informational WARN when two or more stacks of the same category
    are installed (e.g. two backend stacks). The project will work, but the
    later stack wins on conflicting substitution keys — the user should know."""
    if len(report.templates) < 2:
        report.checks.append(
            CheckResult(
                "C12", "category_balance", SEV_PASS,
                "single-stack or base-only project",
            )
        )
        return

    try:
        from cli.stack_registry import load_stack_registry
        registry = load_stack_registry(CODING_OS_ROOT / "templates")
    except Exception:  # noqa: BLE001
        report.checks.append(
            CheckResult(
                "C12", "category_balance", SEV_PASS,
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
        details = ", ".join(
            f"{cat}: {', '.join(ids)}" for cat, ids in duplicates.items()
        )
        report.checks.append(
            CheckResult(
                "C12", "category_balance", SEV_WARN,
                f"multiple stacks in same category ({details}) — last stack wins on conflicts",
                {"duplicates": duplicates},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C12", "category_balance", SEV_PASS,
                f"{len(report.templates)} stacks in {len(categories)} distinct categories",
            )
        )


def _check_stack_skills_linked(project: Path, report: DoctorReport) -> None:
    """C13 — every installed stack's skills are symlinked into the agent's skills dir.

    Detects the B1 regression where `.claude/skills/python-django/SKILL.md`
    was missing even though `--template django` was declared. We consult the
    adapter registry to find `skills_dir` (null for Codex → skip check) and
    the templates/<stack>/skills/ source of truth.
    """
    if not report.templates:
        report.checks.append(
            CheckResult("C13", "stack_skills_linked", SEV_PASS, "no stacks installed")
        )
        return
    if not report.agent:
        report.checks.append(
            CheckResult("C13", "stack_skills_linked", SEV_PASS, "no agent configured")
        )
        return
    try:
        from cli.adapter_registry import load_adapter_registry
        adapters = load_adapter_registry(CODING_OS_ROOT / "adapters")
    except Exception as exc:  # noqa: BLE001
        report.checks.append(
            CheckResult(
                "C13", "stack_skills_linked", SEV_WARN,
                f"could not load adapter registry: {exc}",
            )
        )
        return
    profile = adapters.get(report.agent)
    if profile is None or not profile.skills_dir:
        report.checks.append(
            CheckResult(
                "C13", "stack_skills_linked", SEV_PASS,
                f"adapter '{report.agent}' has no skills_dir — skipped",
            )
        )
        return

    skills_dir = project / profile.skills_dir
    expected: list[tuple[str, str]] = []  # (stack, skill_name)
    for stack in report.templates:
        stack_skills = CODING_OS_ROOT / "templates" / stack / "skills"
        if not stack_skills.exists():
            continue
        for entry in stack_skills.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                expected.append((stack, entry.name))

    if not expected:
        report.checks.append(
            CheckResult(
                "C13", "stack_skills_linked", SEV_PASS,
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
                "C13", "stack_skills_linked", SEV_FAIL,
                f"missing stack skill links: {', '.join(missing)} "
                f"— run `cos update` to repair",
                {"missing": missing},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C13", "stack_skills_linked", SEV_PASS,
                f"all {len(expected)} stack skill(s) linked",
            )
        )


def _check_mcp_portable(project: Path, report: DoctorReport) -> None:
    """C14 — .mcp.json coding-os entry uses the `cos server-start` wrapper.

    The wrapper form lets the project survive coding-os relocations and
    upgrades: the `cos` binary on PATH resolves the server location, no
    absolute dev path is hardcoded. A plain `uv run --directory <abs>`
    entry is tolerated as a bootstrap fallback but flagged WARN.
    """
    mcp_path = project / ".mcp.json"
    if not mcp_path.exists():
        report.checks.append(
            CheckResult("C14", "mcp_portable", SEV_PASS, "no .mcp.json (skip)")
        )
        return
    try:
        import json as _json
        data = _json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        report.checks.append(
            CheckResult("C14", "mcp_portable", SEV_FAIL, f"invalid JSON: {exc}")
        )
        return
    entry = (data.get("mcpServers") or {}).get("coding-os")
    if entry is None:
        report.checks.append(
            CheckResult(
                "C14", "mcp_portable", SEV_PASS,
                "no coding-os MCP entry (skip)",
            )
        )
        return
    command = entry.get("command")
    if command == "cos":
        report.checks.append(
            CheckResult(
                "C14", "mcp_portable", SEV_PASS,
                "uses `cos server-start` wrapper (portable)",
            )
        )
        return
    args = entry.get("args") or []
    has_abs_cos_path = any(
        isinstance(a, str) and "/core/thinking-os" in a for a in args
    )
    if has_abs_cos_path:
        report.checks.append(
            CheckResult(
                "C14", "mcp_portable", SEV_WARN,
                "hardcoded absolute path — runs fine locally but won't "
                "survive coding-os relocation. Install `cos` on PATH and "
                "re-run the adapter install to switch to the wrapper.",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "C14", "mcp_portable", SEV_PASS,
                f"unknown command form '{command}' — assumed portable",
            )
        )


def _load_coding_os_mcp_launch(
    project: Path,
    agent: str | None,
) -> tuple[str | None, list[str], dict[str, str], str | None, str | None]:
    """Return the coding-os MCP launch config from Claude or Codex sources."""

    def _load_claude_json(path: Path) -> tuple[str | None, list[str], dict[str, str], str | None, str | None] | None:
        if not path.exists():
            return None
        try:
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
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
            for key, value in re.findall(r'"((?:[^"\\]|\\.)*)"[ \t]*=[ \t]*"((?:[^"\\]|\\.)*)"', env_match.group(1)):
                env[bytes(key, "utf-8").decode("unicode_escape")] = bytes(value, "utf-8").decode("unicode_escape")
        return cmd_match.group(1), args, env

    def _load_codex(path: Path) -> tuple[str | None, list[str], dict[str, str], str | None, str | None] | None:
        loaded = _load_codex_toml(path)
        if loaded is None:
            return None
        command, args, env = loaded
        return command, args, env, str(path), None

    loaders: list[tuple[str, Path]] = []
    if agent == "claude":
        loaders = [("claude", project / ".mcp.json")]
    elif agent == "codex":
        loaders = [
            ("codex", project / ".codex" / "config.toml"),
            ("codex", Path.home() / ".codex" / "config.toml"),
        ]
    else:
        loaders = [
            ("claude", project / ".mcp.json"),
            ("codex", project / ".codex" / "config.toml"),
            ("codex", Path.home() / ".codex" / "config.toml"),
        ]

    for kind, path in loaders:
        loaded = _load_claude_json(path) if kind == "claude" else _load_codex(path)
        if loaded is not None:
            return loaded

    return None, [], {}, None, None


def _check_mcp_actually_launches(project: Path, report: DoctorReport) -> None:
    """C15 — simulate the exact MCP launch path the active agent config uses.

    C10 runs `server.py --test` with an explicit COS_DB_PATH env — that
    verifies the server code works but bypasses the agent launch config
    entirely. C15 closes that gap: it reads coding-os MCP launch config
    from Claude or Codex, runs the declared command with the project
    root as cwd, feeds a real `initialize` handshake, and expects a
    valid JSON-RPC response.
    """
    command, args, entry_env, source_path, load_error = _load_coding_os_mcp_launch(
        project, report.agent
    )
    if load_error:
        report.checks.append(
            CheckResult("C15", "mcp_actually_launches", SEV_FAIL, load_error)
        )
        return
    if source_path is None:
        report.checks.append(
            CheckResult(
                "C15", "mcp_actually_launches", SEV_FAIL,
                "coding-os MCP config missing — neither .mcp.json nor "
                ".codex/config.toml defines coding-os. Run "
                "`bash <coding-os>/adapters/claude/install.sh` or "
                "`bash <coding-os>/adapters/codex/install.sh` from the project root.",
            )
        )
        return
    if command is None:
        report.checks.append(
            CheckResult(
                "C15", "mcp_actually_launches", SEV_PASS,
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
                "C15", "mcp_actually_launches", SEV_FAIL,
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
                "C15", "mcp_actually_launches", SEV_FAIL,
                f"command not found on PATH: {command!r}. "
                f"Install via `uv tool install --editable <coding-os>`.",
            )
        )
        return
    except subprocess.TimeoutExpired:
        report.checks.append(
            CheckResult(
                "C15", "mcp_actually_launches", SEV_PASS,
                "launched (exceeded 20s → server is running, no crash)",
            )
        )
        return
    except OSError as exc:
        report.checks.append(
            CheckResult(
                "C15", "mcp_actually_launches", SEV_FAIL,
                f"OS error launching: {exc}",
            )
        )
        return

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if '"jsonrpc"' in (proc.stdout or "") and '"result"' in (proc.stdout or ""):
        report.checks.append(
            CheckResult(
                "C15", "mcp_actually_launches", SEV_PASS,
                "initialize handshake succeeded (server ready)",
            )
        )
        return

    if "unable to open database file" in combined or "OperationalError" in combined:
        msg = (
            "server crashed: cannot open DB. This usually means the "
            "MCP launch config uses `uv run --directory ...` which "
            "chdir's into the server tree, so `.coding-os/thinking-os.db` "
            "stops resolving. Switch to the wrapper form: "
            '`command = "cos"` and `args = ["server-start"]`.'
        )
    elif "No module named" in combined or "ModuleNotFoundError" in combined:
        msg = "server crashed: missing Python dependency — rerun `uv sync`."
    else:
        tail = combined.strip().splitlines()[-3:]
        msg = (
            f"launch failed (exit {proc.returncode}). Last output: "
            + " | ".join(tail)[-200:]
        )

    report.checks.append(
        CheckResult(
            "C15", "mcp_actually_launches", SEV_FAIL, msg,
            {"stderr_tail": (proc.stderr or "")[-500:]},
        )
    )


def _check_agents_md_present(project: Path, report: DoctorReport) -> None:
    """C16 — AGENTS.md at the project root is the canonical instruction file.

    Read by both Claude (via AGENTS.md convention) and Codex. `cos init`
    generates it; pre-v0.2.0 projects or partial installs may be missing it.
    `cos add-adapter` and `cos update` now backfill automatically — this
    check catches projects that never ran either command since.
    """
    agents_md = project / "AGENTS.md"
    if agents_md.exists():
        report.checks.append(
            CheckResult(
                "C16", "agents_md_present", SEV_PASS, "present",
                {"path": str(agents_md.relative_to(project))},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "C16", "agents_md_present", SEV_FAIL,
            "missing — run 'cos update' or 'cos add-adapter <agent>' to backfill",
            {"expected": "AGENTS.md"},
        )
    )


def _format_text(report: DoctorReport, *, strict: bool) -> str:
    header = (
        f"Coding OS Doctor — {report.project_dir}\n"
        f"Agent: {report.agent or '?'}    Templates: {', '.join(report.templates) or 'none'}\n"
        + "=" * 60
    )
    lines = [header]
    for c in report.checks:
        badge = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[c.severity]
        lines.append(f"{badge} {c.id} {c.name:24s} {c.message}")
    s = report.summary()
    lines.append("-" * 60)
    lines.append(
        f"Summary: {s['pass']} PASS, {s['warn']} WARN, {s['fail']} FAIL "
        f"(exit={report.exit_code(strict=strict)})"
    )
    return "\n".join(lines)


def _format_json(report: DoctorReport, *, strict: bool) -> str:
    payload = {
        "project_dir": report.project_dir,
        "agent": report.agent,
        "templates": report.templates,
        "checks": [asdict(c) for c in report.checks],
        "summary": {**report.summary(), "exit_code": report.exit_code(strict=strict)},
    }
    return json.dumps(payload, indent=2)


@click.command()
@click.option("--project-dir", "-d", default=".", help="Project directory (default: cwd)")
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.option("--strict", is_flag=True, default=False, help="Promote WARN to exit 1")
@click.option("--manifest", default=None, help="Override manifest file path")
def doctor(project_dir: str, output_format: str, strict: bool, manifest: str | None) -> None:
    """Deep health check: scaffold, DB schema, adapter, manifest, MCP."""
    project = Path(project_dir).resolve()
    manifest_path = Path(manifest).resolve() if manifest else None
    report = run_doctor(project, manifest_path=manifest_path)
    if output_format == "json":
        click.echo(_format_json(report, strict=strict))
    else:
        click.echo(_format_text(report, strict=strict))
    sys.exit(report.exit_code(strict=strict))
