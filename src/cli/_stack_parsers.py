"""Manifest schema validation and the per-field parsers for stack.yaml rows."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from jsonschema import Draft202012Validator, ValidationError as _JSValidationError

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover — dependency pinned in pyproject.toml
    _HAS_JSONSCHEMA = False
    _JSValidationError = Exception  # type: ignore

from cli._data_types import (
    AgentsMdSection,
    DimensionEntry,
    HookEntry,
    MakefileTarget,
    RefCode,
    RuleEntry,
    SkillEnforcementEntry,
    StackProfile,
    VerifyRow,
)
from cli._resources import core_dir as _core_dir

logger = logging.getLogger(__name__)

STACK_MANIFEST_NAME = "stack.yaml"
BASE_MANIFEST_NAME = "base.yaml"
SUPPORTED_VERSION = 1

# Resolved via importlib — survives wheel installs and meta-repo moves.
_SCHEMA_DIR = _core_dir("schemas")
_STACK_SCHEMA_PATH = _SCHEMA_DIR / "stack.schema.json"


@lru_cache(maxsize=1)
def _stack_schema_validator() -> Draft202012Validator | None:
    """Lazy-load the stack.yaml JSON schema validator.

    Returns None if jsonschema is not installed or the schema file is
    missing — in that case we fall back to the handwritten field-by-field
    validation below so the loader still works.
    """
    if not _HAS_JSONSCHEMA:
        return None
    if not _STACK_SCHEMA_PATH.exists():
        logger.warning("stack schema not found at %s", _STACK_SCHEMA_PATH)
        return None
    try:
        schema = json.loads(_STACK_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to load stack schema: %s", exc)
        return None
    return Draft202012Validator(schema)


def _jsonschema_validate_stack(data: dict, manifest_path: Path) -> None:
    """Validate a stack manifest against the JSON schema.

    Raises StackManifestError with all errors concatenated. If jsonschema
    is unavailable, this is a no-op (handwritten parsing still runs).
    """
    validator = _stack_schema_validator()
    if validator is None:
        return
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return
    messages = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        messages.append(f"{loc}: {err.message}")
    joined = "; ".join(messages)
    raise StackManifestError(f"{manifest_path}: schema validation failed — {joined}")


class StackManifestError(ValueError):
    """Raised when a stack.yaml is structurally invalid."""


@dataclass(frozen=True)
class StackLoadResult:
    """Result of loading a stack registry — separates success/warnings."""

    stacks: dict[str, StackProfile]
    warnings: tuple[str, ...]

    def __iter__(self):  # type: ignore[override]
        return iter(self.stacks)

    def __getitem__(self, key: str) -> StackProfile:
        return self.stacks[key]

    def __contains__(self, key: str) -> bool:
        return key in self.stacks

    def keys(self):
        return self.stacks.keys()

    def values(self):
        return self.stacks.values()

    def items(self):
        return self.stacks.items()


def _require(data: dict, key: str, manifest_path: Path) -> Any:
    if key not in data:
        raise StackManifestError(f"{manifest_path}: missing required key '{key}'")
    return data[key]


def _require_item_key(item: dict, key: str, path: Path, context: str) -> Any:
    """Like _require but for nested dicts, includes context (field[idx])."""
    if key not in item:
        raise StackManifestError(f"{path}: {context} missing required key '{key}'")
    return item[key]


def _as_tuple_of_str(value: Any, path: Path, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise StackManifestError(f"{path}: '{field}' must be a list, got {type(value).__name__}")
    return tuple(str(v) for v in value)


def _parse_verify_rows(raw: Any, path: Path) -> tuple[VerifyRow, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'verify' must be a list")
    rows = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: verify[{i}] must be a mapping")
        rows.append(
            VerifyRow(
                glob=str(item.get("glob", "")),
                suites=str(item.get("suites", "")),
                cmd=str(item.get("cmd", "")),
            )
        )
    return tuple(rows)


def _parse_ref_codes(raw: Any, path: Path) -> tuple[RefCode, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'ref_codes' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: ref_codes[{i}] must be a mapping")
        out.append(
            RefCode(
                code=str(item.get("code", "")),
                path=str(item.get("path", "")),
                desc=str(item.get("desc", "")),
            )
        )
    return tuple(out)


def _parse_makefile_targets(raw: Any, path: Path) -> tuple[MakefileTarget, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'makefile_targets' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: makefile_targets[{i}] must be a mapping")
        ctx = f"makefile_targets[{i}]"
        out.append(
            MakefileTarget(
                name=str(_require_item_key(item, "name", path, ctx)),
                cmd=str(_require_item_key(item, "cmd", path, ctx)),
                help=str(item.get("help", "")),
            )
        )
    return tuple(out)


def _parse_rules(raw: Any, path: Path) -> tuple[RuleEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'rules' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: rules[{i}] must be a mapping")
        ctx = f"rules[{i}]"
        out.append(
            RuleEntry(
                file=str(_require_item_key(item, "file", path, ctx)),
                globs=_as_tuple_of_str(item.get("globs"), path, f"{ctx}.globs"),
                always_load=bool(item.get("always_load", False)),
                priority=int(item.get("priority", 0)),
            )
        )
    return tuple(out)


def _parse_dimensions(raw: Any, path: Path, stack_id: str) -> tuple[DimensionEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'dimensions' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: dimensions[{i}] must be a mapping")
        ctx = f"dimensions[{i}]"
        out.append(
            DimensionEntry(
                stack_id=stack_id,
                name=str(_require_item_key(item, "name", path, ctx)),
                read_files=_as_tuple_of_str(item.get("read_files"), path, f"{ctx}.read_files"),
                depth=str(item.get("depth", "M")),
            )
        )
    return tuple(out)


def _parse_skill_enforcement(
    raw: Any, path: Path, stack_id: str
) -> tuple[SkillEnforcementEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'skill_enforcement' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: skill_enforcement[{i}] must be a mapping")
        ctx = f"skill_enforcement[{i}]"
        out.append(
            SkillEnforcementEntry(
                stack_id=stack_id,
                globs=_as_tuple_of_str(item.get("globs"), path, f"{ctx}.globs"),
                primary=str(_require_item_key(item, "primary", path, ctx)),
                secondary=_as_tuple_of_str(item.get("secondary"), path, f"{ctx}.secondary"),
            )
        )
    return tuple(out)


def _parse_sections(raw: Any, path: Path, owner_dir: Path) -> tuple[AgentsMdSection, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'agents_md_sections' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: agents_md_sections[{i}] must be a mapping")
        ctx = f"agents_md_sections[{i}]"
        out.append(
            AgentsMdSection(
                id=str(_require_item_key(item, "id", path, ctx)),
                order=int(_require_item_key(item, "order", path, ctx)),
                template=str(_require_item_key(item, "template", path, ctx)),
                owner_dir=owner_dir,
            )
        )
    return tuple(out)


def _parse_hooks(raw: Any, path: Path) -> tuple[HookEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise StackManifestError(f"{path}: 'hooks' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StackManifestError(f"{path}: hooks[{i}] must be a mapping")
        ctx = f"hooks[{i}]"
        out.append(
            HookEntry(
                event=str(_require_item_key(item, "event", path, ctx)),
                matcher=str(item.get("matcher", "*")),
                command=str(_require_item_key(item, "command", path, ctx)),
            )
        )
    return tuple(out)


def _load_yaml(path: Path, *, validate_schema: bool = True) -> dict:
    """Parse + optionally schema-validate a stack/base manifest.

    `validate_schema=True` runs jsonschema against `stack.schema.json`
    first. Base manifests (`base.yaml`) skip schema validation because
    they have a slightly different shape (no id-matches-dirname rule).
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise StackManifestError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StackManifestError(f"{path}: top level must be a mapping")
    version = data.get("version")
    if version != SUPPORTED_VERSION:
        raise StackManifestError(
            f"{path}: unsupported version {version!r}, expected {SUPPORTED_VERSION}"
        )
    if validate_schema:
        _jsonschema_validate_stack(data, path)
    return data
