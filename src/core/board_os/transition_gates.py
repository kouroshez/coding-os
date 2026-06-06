"""Transition Gates — DoR / DoD / WIP / size / override policy."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

# ────────────────────────────────────────────────────────────────────
# Section rules
# ────────────────────────────────────────────────────────────────────


class SectionRule(BaseModel):
    """Per-section content requirements within a task body.

    Two flavors of forbidden content for clarity:
      forbid_substrings — plain string `in` check (YAML-friendly, no escapes).
      forbid_regex      — full regex (use sparingly; YAML must escape).
    """

    required: bool = False
    min_chars: int = 0
    min_items: int = 0  # for list-shaped sections like "Read First"
    required_subitems: list[str] = Field(default_factory=list)
    forbid_substrings: list[str] = Field(default_factory=list)
    forbid_regex: list[str] = Field(default_factory=list)
    # Legacy alias kept for one release; merged into forbid_substrings on load.
    forbid_patterns: list[str] = Field(default_factory=list, exclude=True)

    def model_post_init(self, __context: Any) -> None:
        if self.forbid_patterns and not self.forbid_substrings:
            # Migrate legacy field to substrings to preserve the safer default.
            object.__setattr__(self, "forbid_substrings", list(self.forbid_patterns))


class DoRKindRules(BaseModel):
    """Definition-of-Ready rules for one kind (or the default).

    Per-section value semantics (strategic-merge-patch style):
        SectionRule object → replace this section's rules wholesale
        None               → remove this section from requirements (kind
                             explicitly opts out of a default rule)
        omitted            → inherit from default
    """

    sections: dict[str, SectionRule | None] = Field(default_factory=dict)


class DoRConfig(BaseModel):
    """Top-level Definition-of-Ready: default + per-kind overrides."""

    default: DoRKindRules = Field(default_factory=DoRKindRules)
    by_kind: dict[str, DoRKindRules] = Field(default_factory=dict)

    def for_kind(self, kind: str) -> DoRKindRules:
        """Resolve effective rules for a kind via strategic-merge-patch.

        - kind with section value `None` → drop that section entirely.
        - kind with section value SectionRule → replace default's rule.
        - kind that omits a section → inherit default's rule.
        - kind not in by_kind → return default verbatim.
        """
        if kind not in self.by_kind:
            return DoRKindRules(
                sections={n: r for n, r in self.default.sections.items() if r is not None},
            )
        merged: dict[str, SectionRule | None] = deepcopy(self.default.sections)
        for name, rule in self.by_kind[kind].sections.items():
            merged[name] = rule
        # Drop None entries — the kind explicitly disabled them.
        return DoRKindRules(
            sections={n: r for n, r in merged.items() if r is not None},
        )


# ────────────────────────────────────────────────────────────────────
# DoD
# ────────────────────────────────────────────────────────────────────


class DoDKindRules(BaseModel):
    """Definition-of-Done rules for one kind."""

    require_verify: bool = True
    verify_max_age_seconds: int = 1800
    require_work_log: bool = True


class DoDConfig(BaseModel):
    default: DoDKindRules = Field(default_factory=DoDKindRules)
    by_kind: dict[str, DoDKindRules] = Field(default_factory=dict)

    def for_kind(self, kind: str) -> DoDKindRules:
        if kind not in self.by_kind:
            return self.default
        # DoD rules are flat — kind block overrides field-by-field.
        merged = self.default.model_dump()
        merged.update({k: v for k, v in self.by_kind[kind].model_dump().items() if v is not None})
        return DoDKindRules(**merged)


# ────────────────────────────────────────────────────────────────────
# WIP / size / overrides
# ────────────────────────────────────────────────────────────────────


class WipLimits(BaseModel):
    in_progress: int = 1
    testing: int = 3
    emergency: int = 2

    @field_validator("in_progress", "testing", "emergency")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("wip limit must be >= 0")
        return v


class SizeLimits(BaseModel):
    warn_tokens: int = 1500
    block_tokens: int = 3000

    @field_validator("block_tokens")
    @classmethod
    def _block_above_warn(cls, v: int, info: Any) -> int:
        warn = info.data.get("warn_tokens", 0)
        if v < warn:
            raise ValueError(f"block_tokens ({v}) must be >= warn_tokens ({warn})")
        return v


class OverridePolicy(BaseModel):
    require_reason: bool = True
    min_reason_chars: int = 15
    audit_to: str = "task_status_history.override_reason"


# ────────────────────────────────────────────────────────────────────
# Top-level config
# ────────────────────────────────────────────────────────────────────


class GatesConfig(BaseModel):
    """SSOT — the parsed `transition-gates.yaml`."""

    version: int = 1
    definition_of_ready: DoRConfig = Field(default_factory=DoRConfig)
    definition_of_done: DoDConfig = Field(default_factory=DoDConfig)
    wip_limits: WipLimits = Field(default_factory=WipLimits)
    size_limits: SizeLimits = Field(default_factory=SizeLimits)
    overrides: OverridePolicy = Field(default_factory=OverridePolicy)


# ────────────────────────────────────────────────────────────────────
# Loader
# ────────────────────────────────────────────────────────────────────


DEFAULT_GATES_PATH = Path(__file__).resolve().parent / "transition-gates.yaml"


class GatesConfigError(ValueError):
    """Raised when the YAML is malformed or fails Pydantic validation."""


def load_gates_config(path: Path | str | None = None) -> GatesConfig:
    """Read and parse a transition-gates.yaml file.

    A missing file falls back to *built-in defaults* (i.e. an empty
    GatesConfig with library defaults), not a crash. This means a
    consumer project that hasn't run `cos sync-all` still gets sane
    behavior; the SSOT just isn't customized.

    Malformed YAML or schema-violating content raises GatesConfigError
    with the underlying exception attached as `__cause__`.
    """
    target = Path(path) if path is not None else DEFAULT_GATES_PATH
    if not target.exists():
        return GatesConfig()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise GatesConfigError(f"transition-gates: malformed YAML at {target}: {exc}") from exc
    try:
        return GatesConfig.model_validate(raw)
    except Exception as exc:
        raise GatesConfigError(f"transition-gates: schema violation at {target}: {exc}") from exc


def load_gates_from_str(content: str) -> GatesConfig:
    """Test helper: parse YAML content directly without disk I/O."""
    try:
        raw = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise GatesConfigError(f"transition-gates: malformed YAML: {exc}") from exc
    try:
        return GatesConfig.model_validate(raw)
    except Exception as exc:
        raise GatesConfigError(f"transition-gates: schema violation: {exc}") from exc


__all__ = [
    "DEFAULT_GATES_PATH",
    "DoDConfig",
    "DoDKindRules",
    "DoRConfig",
    "DoRKindRules",
    "GatesConfig",
    "GatesConfigError",
    "OverridePolicy",
    "SectionRule",
    "SizeLimits",
    "WipLimits",
    "load_gates_config",
    "load_gates_from_str",
]
