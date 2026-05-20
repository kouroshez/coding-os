"""Data-driven verify-suite resolution (Phase L.10 / TASK-100)."""

from __future__ import annotations

import fnmatch
import os
from copy import deepcopy
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_VERIFY_SUITES_YAML = Path(__file__).resolve().parent / "verify-suites.yaml"


class SuiteRule(BaseModel):
    paths: list[str] = Field(default_factory=list)
    command: str
    max_age_seconds: int | None = None


class VerifySuitesConfig(BaseModel):
    version: int = 1
    suites: dict[str, SuiteRule] = Field(default_factory=dict)
    defaults: dict = Field(default_factory=lambda: {"max_age_seconds": 1800})


class VerifySuitesError(ValueError):
    """Raised on malformed YAML or schema violations."""


def _load_one(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise VerifySuitesError(f"verify-suites: malformed YAML at {path}: {exc}") from exc


def load_verify_suites(
    *,
    meta_path: Path | None = None,
    project_root: Path | None = None,
) -> VerifySuitesConfig:
    """Load meta defaults, optionally overlaid with consumer overrides.

    Consumer override path: `${project_root}/.coding-os/verify-suites.yaml`.
    A suite that appears in both takes the consumer version verbatim
    (whole-suite replacement, not partial merge — keeps consumer rules
    auditable as a single block).
    """
    meta = _load_one(meta_path or DEFAULT_VERIFY_SUITES_YAML)
    if project_root is None:
        project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd()))
    consumer_path = project_root / ".coding-os" / "verify-suites.yaml"
    consumer = _load_one(consumer_path) if consumer_path.exists() else {}

    merged = deepcopy(meta)
    if "suites" not in merged:
        merged["suites"] = {}
    for name, rule in (consumer.get("suites") or {}).items():
        merged["suites"][name] = rule
    if "defaults" in consumer:
        merged.setdefault("defaults", {}).update(consumer["defaults"])

    try:
        return VerifySuitesConfig.model_validate(merged)
    except Exception as exc:
        raise VerifySuitesError(f"verify-suites: schema violation: {exc}") from exc


def match_suites(
    changed_paths: list[str],
    config: VerifySuitesConfig,
) -> list[str]:
    """Return the ordered list of suite names whose globs match any path.

    Order is deterministic: dictionary iteration over the merged
    config (insertion order). A suite with no `paths:` never matches —
    it must be explicitly invoked.
    """
    if not changed_paths:
        return []
    matched: list[str] = []
    for name, rule in config.suites.items():
        if not rule.paths:
            continue
        for changed in changed_paths:
            if any(_glob_match(p, changed) for p in rule.paths):
                matched.append(name)
                break
    return matched


def _glob_match(pattern: str, path: str) -> bool:
    """fnmatch-based glob with `**` recursive support.

    fnmatch alone treats `**` as `*`; we expand `**/` to match any
    number of directory components.
    """
    normalised = pattern.replace("**/", "*/").replace("/**", "/*")
    if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, normalised):
        return True
    if "**" in pattern:
        flat = pattern.replace("**/", "").replace("/**", "")
        if fnmatch.fnmatch(path, flat):
            return True
    return False


def get_suite_command(name: str, config: VerifySuitesConfig) -> str | None:
    """Return the run-command for a named suite, or None if unknown."""
    rule = config.suites.get(name)
    return rule.command if rule else None


__all__ = [
    "DEFAULT_VERIFY_SUITES_YAML",
    "SuiteRule",
    "VerifySuitesConfig",
    "VerifySuitesError",
    "get_suite_command",
    "load_verify_suites",
    "match_suites",
]
