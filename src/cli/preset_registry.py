"""Discover and load project presets from src/templates/_presets/<id>.yaml.

A preset is a named stack composition picked at init (`cos init --preset`).
Invalid or unknown-stack presets are skipped with a WARN, not a crash —
same fail-soft posture as the stack loader. SSOT:
docs/engineering/config-composition.md § Presets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

try:
    from jsonschema import Draft202012Validator

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover — dependency pinned in pyproject.toml
    _HAS_JSONSCHEMA = False

from cli._resources import core_dir as _core_dir

logger = logging.getLogger(__name__)

PRESETS_DIRNAME = "_presets"
_PRESET_SCHEMA_PATH = _core_dir("schemas") / "preset.schema.json"


def user_presets_dir() -> Path:
    """Where user-authored presets live (cos preset create/import).

    Override with $COS_USER_PRESETS_DIR (tests, shared machines)."""
    import os

    override = os.environ.get("COS_USER_PRESETS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".coding-os" / "presets"


@dataclass(frozen=True)
class PresetProfile:
    """One project preset. Loaded from templates/_presets/<id>.yaml."""

    id: str
    label: str
    stacks: tuple[str, ...]
    description: str = ""
    skills: tuple[str, ...] = ()
    modules: dict[str, bool] = field(default_factory=dict)
    source_path: Path = Path(".")


@dataclass(frozen=True)
class PresetLoadResult:
    """Result of loading the preset registry — separates success/warnings."""

    presets: dict[str, PresetProfile]
    warnings: tuple[str, ...]

    def __iter__(self):  # type: ignore[override]
        return iter(self.presets)

    def __getitem__(self, key: str) -> PresetProfile:
        return self.presets[key]

    def __contains__(self, key: str) -> bool:
        return key in self.presets

    def keys(self):
        return self.presets.keys()

    def values(self):
        return self.presets.values()

    def items(self):
        return self.presets.items()


@lru_cache(maxsize=1)
def _preset_schema_validator():
    if not _HAS_JSONSCHEMA or not _PRESET_SCHEMA_PATH.is_file():
        return None
    import json

    return Draft202012Validator(json.loads(_PRESET_SCHEMA_PATH.read_text(encoding="utf-8")))


def _validate(data: dict, path: Path) -> list[str]:
    validator = _preset_schema_validator()
    if validator is None:
        return []
    return [
        f"{path.name}: {err.json_path}: {err.message}"
        for err in validator.iter_errors(data)
    ]


def load_preset_registry(
    templates_dir: Path,
    known_stacks: set[str] | None = None,
    include_user: bool = True,
) -> PresetLoadResult:
    """Scan templates_dir/_presets (+ the user preset dir) for *.yaml.

    Repo presets win on id collision (a user file shadowing a shipped preset
    is skipped with a WARN). When `known_stacks` is given, a preset
    referencing a stack outside it is skipped with a WARN.
    """
    presets: dict[str, PresetProfile] = {}
    warnings: list[str] = []

    manifests: list[Path] = []
    presets_dir = templates_dir / PRESETS_DIRNAME
    if presets_dir.is_dir():
        manifests.extend(sorted(presets_dir.glob("*.yaml")))
    if include_user and user_presets_dir().is_dir():
        manifests.extend(sorted(user_presets_dir().glob("*.yaml")))
    if not manifests:
        return PresetLoadResult(presets={}, warnings=())

    for manifest in manifests:
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as exc:
            warnings.append(f"skipping preset {manifest.name}: unreadable YAML ({exc})")
            continue
        if not isinstance(data, dict):
            warnings.append(f"skipping preset {manifest.name}: not a YAML mapping")
            continue

        schema_errors = _validate(data, manifest)
        if schema_errors:
            warnings.extend(f"skipping preset: {e}" for e in schema_errors)
            continue
        if data["id"] != manifest.stem:
            warnings.append(
                f"skipping preset {manifest.name}: id '{data['id']}' must match filename stem"
            )
            continue

        stacks = tuple(str(s) for s in data["stacks"])
        if known_stacks is not None:
            unknown = [s for s in stacks if s not in known_stacks]
            if unknown:
                warnings.append(
                    f"skipping preset {data['id']}: unknown stack(s) {unknown} — "
                    f"available: {sorted(known_stacks)}"
                )
                continue

        if data["id"] in presets:
            warnings.append(
                f"skipping preset {manifest}: id '{data['id']}' already shipped — "
                f"repo presets win over user presets"
            )
            continue
        presets[data["id"]] = PresetProfile(
            id=data["id"],
            label=str(data["label"]),
            stacks=stacks,
            description=str(data.get("description") or ""),
            skills=tuple(str(s) for s in data.get("skills") or ()),
            modules={str(k): bool(v) for k, v in (data.get("modules") or {}).items()},
            source_path=manifest,
        )

    for msg in warnings:
        logger.warning(msg)
    return PresetLoadResult(presets=presets, warnings=tuple(warnings))
