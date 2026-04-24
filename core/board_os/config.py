"""board-os — Scrumban configuration loader and validator (L.0).

Reads `.coding-os/scrumban-config.yaml` from the project root and
returns a typed, validated `ScrumbanConfig`. The config defines which
swimlanes (domains) are valid, which WIP caps apply per column, and
which label families have explicit colours.

Per-project overrides ship in templates/<stack>/scaffold/.coding-os/.
The base default ships in templates/_base/scaffold/.coding-os/.

The four categorization axes (see plan §6.1.1):
  swimlane = domain (config-enum, this file)
  kind     = work type (closed enum, KIND_ENUM below)
  epic     = initiative grouping (optional free string)
  labels   = free tags (no rendering impact)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("coding_os.board_os.config")


# Closed enums — see plan §6.1.1.  These are NOT configurable: card
# colour stability across all repos requires a fixed work-type set.
KIND_ENUM: tuple[str, ...] = (
    "feature",
    "bug",
    "chore",
    "spike",
    "docs",
    "refactor",
    "test",
    "security",
)

STATUS_ENUM: tuple[str, ...] = (
    "icebox",
    "emergency",
    "in_progress",
    "testing",
    "complete",
    "blocked",
    "archive",
)

# "ready" is no longer a status column — it collapses into a label on
# tasks that still live in icebox.  Declared here so the label chip
# renders with a distinct colour in the UI and so lint passes keep it
# out of the KIND_ENUM (KIND == "ready" would shadow the label).
READY_LABEL: str = "ready"

PRIORITY_ENUM: tuple[str, ...] = ("P0", "P1", "P2", "P3")

# Default colour palette per work-type.  Hex codes chosen for
# deuteranopia/protanopia distinguishability (Okabe-Ito-adjacent).
_DEFAULT_KIND_COLORS: dict[str, str] = {
    "feature": "#eab308",   # yellow
    "bug": "#dc2626",       # red
    "chore": "#22c55e",     # green
    "spike": "#3b82f6",     # blue
    "docs": "#a855f7",      # purple
    "refactor": "#14b8a6",  # teal
    "test": "#f59e0b",      # amber
    "security": "#ea580c",  # orange
}

# Identifier regex for swimlane ids, label values, epic ids.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# Hex colour regex (3 or 6 char).
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
# Appetite regex (Shape Up style: 30m, 2h, 1d, 3w, 1cy).
APPETITE_RE = re.compile(r"^\d+(?:m|h|d|w|cy)$")


class ConfigValidationError(ValueError):
    """Raised when scrumban-config.yaml fails schema validation.

    Carries a list of human-readable errors so the CLI can print them
    one per line.  Always includes the offending file path when known.
    """

    def __init__(self, errors: list[str], path: Path | None = None) -> None:
        self.errors = errors
        self.path = path
        header = f"scrumban-config.yaml validation failed ({path or '<inline>'})"
        super().__init__(header + ":\n  - " + "\n  - ".join(errors))


@dataclass(frozen=True)
class Swimlane:
    """One row on the Scrumban board — a domain / subsystem / team.

    color  — primary band colour (lighter, used for row tint + left strip).
    accent — darker shade for text + 3-4 px border; defaults to color if
             not set, but picking a deliberate darker tone gives the board
             the distinct per-lane identity the prototype was built around
             (see docs/phase-l-scrumban-task-system-plan.md §12 and the
             design bundle in core/web/ui/coding-os-scrumban/).
    """

    id: str
    label: str
    color: str
    description: str = ""
    accent: str = ""

    def effective_accent(self) -> str:
        return self.accent or self.color


@dataclass(frozen=True)
class WipLimits:
    """Per-column WIP caps.  Defaults match the solo-dev defense (1/3/2)."""

    in_progress: int = 1
    testing: int = 3
    emergency: int = 2

    def cap_for(self, status: str) -> int | None:
        """Return cap for a column or None if uncapped (icebox/ready/etc.)."""
        return {
            "in_progress": self.in_progress,
            "testing": self.testing,
            "emergency": self.emergency,
        }.get(status)


@dataclass(frozen=True)
class LabelFamily:
    """A named label family with a colour override (optional)."""

    name: str
    color: str
    emoji: str = ""


@dataclass(frozen=True)
class ScrumbanConfig:
    """
    PURPOSE:      Typed view of `.coding-os/scrumban-config.yaml`.
    INPUT:        load_config(project_root) discovers + parses YAML.
    OUTPUT:       Frozen dataclass; safe to share across threads.
    DEPENDENCIES: PyYAML.
    NOTES:        kind colours are NOT in this struct — they live in
                  _DEFAULT_KIND_COLORS because they must be stable
                  across all repos for card-colour muscle memory.
                  Per-project config can define EXTRA label_families
                  but cannot override kind colours.
    """

    swimlanes: tuple[Swimlane, ...]
    wip_limits: WipLimits = field(default_factory=WipLimits)
    label_families: tuple[LabelFamily, ...] = field(default_factory=tuple)
    source_path: Path | None = None

    @property
    def swimlane_ids(self) -> set[str]:
        return {sl.id for sl in self.swimlanes}

    def get_swimlane(self, swimlane_id: str) -> Swimlane | None:
        for sl in self.swimlanes:
            if sl.id == swimlane_id:
                return sl
        return None

    def kind_color(self, kind: str) -> str:
        """Return the stable card colour for a work-type."""
        return _DEFAULT_KIND_COLORS.get(kind, "#6b7280")  # gray fallback


def _validate_id(value: Any, field_name: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _ID_RE.match(value):
        errors.append(
            f"{field_name}={value!r} must match {_ID_RE.pattern}"
        )


def _validate_color(value: Any, field_name: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _HEX_RE.match(value):
        errors.append(
            f"{field_name}={value!r} must be a hex colour (#rgb or #rrggbb)"
        )


def parse_config(data: dict[str, Any], source_path: Path | None = None) -> ScrumbanConfig:
    """
    PURPOSE:      Parse a dict into ScrumbanConfig with full validation.
    INPUT:        data = parsed YAML; source_path optional for errors.
    OUTPUT:       ScrumbanConfig on success; raises ConfigValidationError.
    DEPENDENCIES: none (pure).
    NOTES:        Used by load_config + tests.  Idempotent.
    """
    errors: list[str] = []

    # swimlanes (required, non-empty)
    swimlanes_raw = data.get("swimlanes")
    if not isinstance(swimlanes_raw, list) or not swimlanes_raw:
        errors.append("swimlanes must be a non-empty list")
        raise ConfigValidationError(errors, path=source_path)

    seen_ids: set[str] = set()
    swimlanes: list[Swimlane] = []
    for i, sl in enumerate(swimlanes_raw):
        if not isinstance(sl, dict):
            errors.append(f"swimlanes[{i}] must be a mapping")
            continue
        sid = sl.get("id")
        _validate_id(sid, f"swimlanes[{i}].id", errors)
        if isinstance(sid, str) and sid in seen_ids:
            errors.append(f"swimlanes[{i}].id={sid!r} is duplicated")
        if isinstance(sid, str):
            seen_ids.add(sid)
        label = sl.get("label", sid if isinstance(sid, str) else "")
        if not isinstance(label, str):
            errors.append(f"swimlanes[{i}].label must be a string")
            label = ""
        color = sl.get("color", "#6b7280")
        _validate_color(color, f"swimlanes[{i}].color", errors)
        accent = sl.get("accent", color)
        _validate_color(accent, f"swimlanes[{i}].accent", errors)
        description = sl.get("description", "")
        if not isinstance(description, str):
            errors.append(f"swimlanes[{i}].description must be a string")
            description = ""
        if (
            isinstance(sid, str)
            and isinstance(label, str)
            and isinstance(color, str)
            and isinstance(accent, str)
        ):
            swimlanes.append(
                Swimlane(
                    id=sid,
                    label=label,
                    color=color,
                    accent=accent,
                    description=description,
                )
            )

    # wip_limits (optional)
    wip_raw = data.get("wip_limits", {}) or {}
    if not isinstance(wip_raw, dict):
        errors.append("wip_limits must be a mapping")
        wip_raw = {}
    wip_kwargs: dict[str, int] = {}
    for col in ("in_progress", "testing", "emergency"):
        if col in wip_raw:
            v = wip_raw[col]
            if not isinstance(v, int) or v < 0:
                errors.append(f"wip_limits.{col}={v!r} must be a non-negative int")
            else:
                wip_kwargs[col] = v
    wip_limits = WipLimits(**wip_kwargs)

    # label_families (optional)
    label_families_raw = data.get("label_families", []) or []
    if not isinstance(label_families_raw, list):
        errors.append("label_families must be a list")
        label_families_raw = []
    label_families: list[LabelFamily] = []
    seen_lf: set[str] = set()
    for i, lf in enumerate(label_families_raw):
        if not isinstance(lf, dict):
            errors.append(f"label_families[{i}] must be a mapping")
            continue
        name = lf.get("name")
        _validate_id(name, f"label_families[{i}].name", errors)
        if isinstance(name, str) and name in KIND_ENUM:
            errors.append(
                f"label_families[{i}].name={name!r} collides with KIND_ENUM "
                f"(use kind, not labels, for {name})"
            )
        if isinstance(name, str) and name in seen_lf:
            errors.append(f"label_families[{i}].name={name!r} is duplicated")
        if isinstance(name, str):
            seen_lf.add(name)
        color = lf.get("color", "#6b7280")
        _validate_color(color, f"label_families[{i}].color", errors)
        emoji = lf.get("emoji", "")
        if not isinstance(emoji, str):
            errors.append(f"label_families[{i}].emoji must be a string")
            emoji = ""
        if isinstance(name, str) and isinstance(color, str):
            label_families.append(LabelFamily(name=name, color=color, emoji=emoji))

    if errors:
        raise ConfigValidationError(errors, path=source_path)

    return ScrumbanConfig(
        swimlanes=tuple(swimlanes),
        wip_limits=wip_limits,
        label_families=tuple(label_families),
        source_path=source_path,
    )


def _config_path(project_root: Path) -> Path:
    """Resolve the canonical config path for a project."""
    return project_root / ".coding-os" / "scrumban-config.yaml"


def load_config(project_root: str | os.PathLike[str] | None = None) -> ScrumbanConfig:
    """
    PURPOSE:      Locate and parse the project's scrumban-config.yaml.
    INPUT:        project_root path; defaults to cwd.
    OUTPUT:       ScrumbanConfig; raises FileNotFoundError if config
                  missing, ConfigValidationError if malformed.
    DEPENDENCIES: yaml.safe_load, parse_config.
    NOTES:        No silent fallback to defaults — a missing config
                  is a real configuration bug the user must fix
                  (probably by running `cos board-config --init`).
    """
    root = Path(project_root or os.getcwd()).resolve()
    path = _config_path(root)
    if not path.exists():
        raise FileNotFoundError(
            f"scrumban-config.yaml not found at {path}. "
            f"Run `cos board-config --init` to scaffold a default."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigValidationError(
            ["top-level YAML must be a mapping"], path=path
        )
    return parse_config(data, source_path=path)
