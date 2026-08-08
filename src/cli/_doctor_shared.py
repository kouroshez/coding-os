"""Doctor report types, constants, and shared helpers — leaf module (no doctor import)."""

from __future__ import annotations

# The original cli.doctor import surface lives here in full (and is re-exported
# by the facade) because the doctor_checks_* siblings and external consumers
# address these names through the module namespace.
import contextlib  # noqa: F401
import json  # noqa: F401
import logging
import os
import re
import sqlite3  # noqa: F401
import subprocess  # noqa: F401
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import click  # noqa: F401
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


def _tick(label: str) -> None:
    """Stream a per-check progress line to stderr (interactive runs only)."""
    if sys.stderr.isatty():
        print(f"  [doctor] {label}…", file=sys.stderr, flush=True)


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
    "_DOCTOR_CFG",
    "Any",
    "CheckResult",
    "DoctorReport",
    "Path",
    "_derive_expected_schema_version",
    "_load_doctor_config",
    "_load_runtime_paths",
    "_scan_cfg",
    "_scan_project_files",
    "_schema_cfg",
    "_tick",
    "adapters_dir",
    "annotations",
    "asdict",
    "core_dir",
    "current_core_version",
    "data_root",
    "dataclass",
    "field",
    "logger",
    "read_stamped_version",
    "templates_dir",
]
