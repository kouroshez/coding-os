"""Discover and load stack profiles from src/templates/<id>/stack.yaml.

A stack contributes metadata (label, category, primary skill, …) and
data rows (verify rows, ref codes, makefile targets, rules, …) that
the aggregator merges into the AggregatedWorld.

Invalid stack.yaml files are skipped with a WARN (D9), not a crash —
one bad stack shouldn't break the whole CLI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
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
    BaseProfile,
    DimensionEntry,
    HookEntry,
    MakefileTarget,
    RefCode,
    RuleEntry,
    SkillEnforcementEntry,
    StackProfile,
    VerifyRow,
)

logger = logging.getLogger(__name__)

STACK_MANIFEST_NAME = "stack.yaml"
BASE_MANIFEST_NAME = "base.yaml"
SUPPORTED_VERSION = 1

from cli._resources import core_dir as _core_dir

# Resolved via importlib (TASK-219) — survives wheel installs and meta-repo moves.
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


def _build_stack(data: dict, manifest_path: Path) -> StackProfile:
    source_dir = manifest_path.parent
    stack_id = str(_require(data, "id", manifest_path))
    if stack_id != source_dir.name:
        raise StackManifestError(
            f"{manifest_path}: id '{stack_id}' must match directory name '{source_dir.name}'"
        )
    return StackProfile(
        id=stack_id,
        label=str(_require(data, "label", manifest_path)),
        category=str(_require(data, "category", manifest_path)),
        primary_skill=(str(data["primary_skill"]) if data.get("primary_skill") else None),
        skills=_as_tuple_of_str(data.get("skills"), manifest_path, "skills"),
        substitutions=dict(data.get("substitutions") or {}),
        verify=_parse_verify_rows(data.get("verify"), manifest_path),
        routing_entries=_as_tuple_of_str(
            data.get("routing_entries"), manifest_path, "routing_entries"
        ),
        ref_codes=_parse_ref_codes(data.get("ref_codes"), manifest_path),
        makefile_targets=_parse_makefile_targets(data.get("makefile_targets"), manifest_path),
        rules=_parse_rules(data.get("rules"), manifest_path),
        dimensions=_parse_dimensions(data.get("dimensions"), manifest_path, stack_id),
        skill_enforcement=_parse_skill_enforcement(
            data.get("skill_enforcement"), manifest_path, stack_id
        ),
        agents_md_sections=_parse_sections(
            data.get("agents_md_sections"), manifest_path, source_dir
        ),
        hooks=_parse_hooks(data.get("hooks"), manifest_path),
        source_dir=source_dir,
        language=str(data.get("language") or ""),
        extends=(str(data["extends"]) if data.get("extends") else None),
        structure={k: str(v) for k, v in (data.get("structure") or {}).items()},
    )


def _merge_extended(parent: StackProfile, child: StackProfile) -> StackProfile:
    """Compose child on parent: scalars child-wins, substitutions merge
    parent-first, list fields concatenate parent+child with stable dedup
    (template-authoring.md § Language layer & composition)."""

    def _concat(parent_items: tuple, child_items: tuple) -> tuple:
        seen: set[str] = set()
        merged: list = []
        for item in (*parent_items, *child_items):
            key = repr(item)
            if key not in seen:
                seen.add(key)
                merged.append(item)
        return tuple(merged)

    return replace(
        child,
        substitutions={**parent.substitutions, **child.substitutions},
        skills=_concat(parent.skills, child.skills),
        verify=_concat(parent.verify, child.verify),
        routing_entries=_concat(parent.routing_entries, child.routing_entries),
        ref_codes=_concat(parent.ref_codes, child.ref_codes),
        makefile_targets=_concat(parent.makefile_targets, child.makefile_targets),
        rules=_concat(parent.rules, child.rules),
        dimensions=_concat(parent.dimensions, child.dimensions),
        skill_enforcement=_concat(parent.skill_enforcement, child.skill_enforcement),
        hooks=_concat(parent.hooks, child.hooks),
    )


def _resolve_extends(
    stacks: dict[str, StackProfile], warnings: list[str]
) -> dict[str, StackProfile]:
    resolved: dict[str, StackProfile] = {}

    def _resolve(stack_id: str, chain: tuple[str, ...]) -> StackProfile:
        if stack_id in resolved:
            return resolved[stack_id]
        profile = stacks[stack_id]
        parent_id = profile.extends
        if parent_id:
            if parent_id in chain or parent_id == stack_id:
                raise StackManifestError(
                    f"extends cycle: {' -> '.join((*chain, stack_id, parent_id))}"
                )
            if parent_id not in stacks:
                raise StackManifestError(f"extends unknown stack '{parent_id}'")
            parent = _resolve(parent_id, (*chain, stack_id))
            profile = _merge_extended(parent, profile)
        resolved[stack_id] = profile
        return profile

    out: dict[str, StackProfile] = {}
    for stack_id in stacks:
        try:
            out[stack_id] = _resolve(stack_id, ())
        except StackManifestError as exc:
            msg = f"skipping stack {stack_id}: {exc}"
            warnings.append(msg)
            logger.warning(msg)
    return out


def group_stacks_by_language(
    stacks: dict[str, StackProfile],
) -> dict[str, list[StackProfile]]:
    """Language → stacks (plain stack first, then alphabetical) for discovery."""
    groups: dict[str, list[StackProfile]] = {}
    for profile in stacks.values():
        groups.setdefault(profile.language or "other", []).append(profile)
    for language, members in groups.items():
        members.sort(key=lambda p: (not _is_plain_stack(p), p.id))
    return dict(sorted(groups.items()))


def _is_plain_stack(profile: StackProfile) -> bool:
    return profile.id in (f"{profile.language}-plain", profile.language)


def plain_stack_by_language(stacks: dict[str, StackProfile]) -> dict[str, str]:
    """language → id of its plain stack, for bare-language picks at init.

    An explicit '<language>-plain' stack always wins; a stack whose id equals
    its language (the pre-convention `python`) only fills the gap — order of
    registry iteration must never decide the winner."""
    plain: dict[str, str] = {}
    fallback: dict[str, str] = {}
    for profile in stacks.values():
        if not profile.language:
            continue
        if profile.id == f"{profile.language}-plain":
            plain[profile.language] = profile.id
        elif profile.id == profile.language:
            fallback[profile.language] = profile.id
    return {**fallback, **plain}


def load_stack_registry(templates_dir: Path) -> StackLoadResult:
    """Scan templates_dir for */stack.yaml files, return a registry.

    Directories without stack.yaml are silently ignored. Invalid manifests
    are skipped with a warning string recorded in the result.
    """
    stacks: dict[str, StackProfile] = {}
    warnings: list[str] = []

    if not templates_dir.is_dir():
        warnings.append(f"templates dir not found: {templates_dir}")
        return StackLoadResult(stacks={}, warnings=tuple(warnings))

    for child in sorted(templates_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue  # _base/ is loaded separately
        manifest = child / STACK_MANIFEST_NAME
        if not manifest.exists():
            continue
        try:
            data = _load_yaml(manifest)
            profile = _build_stack(data, manifest)
        except StackManifestError as exc:
            msg = f"skipping stack {child.name}: {exc}"
            warnings.append(msg)
            logger.warning(msg)
            continue
        if profile.id in stacks:
            msg = f"duplicate stack id '{profile.id}' — keeping first"
            warnings.append(msg)
            logger.warning(msg)
            continue
        stacks[profile.id] = profile

    stacks = _resolve_extends(stacks, warnings)
    return StackLoadResult(stacks=stacks, warnings=tuple(warnings))


def load_base_profile(base_dir: Path) -> BaseProfile:
    """Load src/templates/_base/base.yaml into a BaseProfile.

    Raises StackManifestError on any structural problem — base is required,
    it cannot fail soft like stacks do.
    """
    manifest = base_dir / BASE_MANIFEST_NAME
    if not manifest.exists():
        raise StackManifestError(f"{manifest}: file not found")
    # Base profile has a slightly different shape (no category, no
    # primary_skill) so it skips the stack schema.
    data = _load_yaml(manifest, validate_schema=False)
    source_dir = manifest.parent
    return BaseProfile(
        id=str(_require(data, "id", manifest)),
        label=str(_require(data, "label", manifest)),
        skills=_as_tuple_of_str(data.get("skills"), manifest, "skills"),
        substitutions=dict(data.get("substitutions") or {}),
        verify=_parse_verify_rows(data.get("verify"), manifest),
        routing_entries=_as_tuple_of_str(data.get("routing_entries"), manifest, "routing_entries"),
        ref_codes=_parse_ref_codes(data.get("ref_codes"), manifest),
        makefile_targets=_parse_makefile_targets(data.get("makefile_targets"), manifest),
        rules=_parse_rules(data.get("rules"), manifest),
        dimensions=_parse_dimensions(data.get("dimensions"), manifest, "base"),
        skill_enforcement=_parse_skill_enforcement(data.get("skill_enforcement"), manifest, "base"),
        agents_md_sections=_parse_sections(data.get("agents_md_sections"), manifest, source_dir),
        hooks=_parse_hooks(data.get("hooks"), manifest),
        source_dir=source_dir,
    )
