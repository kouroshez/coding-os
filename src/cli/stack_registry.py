"""Discover and load stack profiles from src/templates/<id>/stack.yaml.

A stack contributes metadata (label, category, primary skill, …) and
data rows (verify rows, ref codes, makefile targets, rules, …) that
the aggregator merges into the AggregatedWorld.

Invalid stack.yaml files are skipped with a WARN (D9), not a crash —
one bad stack shouldn't break the whole CLI.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from cli._data_types import BaseProfile, StackProfile
from cli._stack_parsers import (
    BASE_MANIFEST_NAME,
    STACK_MANIFEST_NAME,
    SUPPORTED_VERSION as SUPPORTED_VERSION,
    StackLoadResult,
    StackManifestError,
    _as_tuple_of_str,
    _load_yaml,
    _parse_dimensions,
    _parse_hooks,
    _parse_makefile_targets,
    _parse_ref_codes,
    _parse_rules,
    _parse_sections,
    _parse_skill_enforcement,
    _parse_verify_rows,
    _require,
)
from cli._stack_relocation import (
    _is_plain_stack as _is_plain_stack,
    _roots_collide as _roots_collide,
    group_stacks_by_language as group_stacks_by_language,
    plain_stack_by_language as plain_stack_by_language,
    relocate_profile as relocate_profile,
    resolve_relocated_profiles as resolve_relocated_profiles,
    service_relocations as service_relocations,
)

logger = logging.getLogger(__name__)


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


def _scan_stack_dir(
    src: Path,
    stacks: dict[str, StackProfile],
    warnings: list[str],
    *,
    is_overlay: bool,
) -> None:
    for child in sorted(src.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue  # _base/ is loaded separately
        manifest = child / STACK_MANIFEST_NAME
        if not manifest.exists():
            continue
        try:
            profile = _build_stack(_load_yaml(manifest), manifest)
        except (StackManifestError, OSError) as exc:
            # OSError too: an unreadable community-overlay stack.yaml must skip,
            # never crash the loader (pass-3 review — fail-soft was Manifest-only).
            msg = f"skipping stack {child.name}: {exc}"
            warnings.append(msg)
            logger.warning(msg)
            continue
        if profile.id in stacks:
            msg = (
                f"community stack id '{profile.id}' already loaded (bundled or an earlier "
                f"overlay) — keeping first"
                if is_overlay
                else f"duplicate stack id '{profile.id}' — keeping first"
            )
            warnings.append(msg)
            logger.warning(msg)
            continue
        stacks[profile.id] = profile


def load_stack_registry(
    templates_dir: Path, *, overlay_dirs: tuple[Path, ...] = ()
) -> StackLoadResult:
    """Scan templates_dir (then any out-of-tree overlay_dirs) for */stack.yaml.

    Directories without stack.yaml are silently ignored. Invalid manifests are
    skipped with a warning string recorded in the result. overlay_dirs hold
    community stacks ($COS_USER_TEMPLATES_DIR); a community id may NOT shadow a
    bundled stack — the bundled profile is kept (scanned first).

    overlay_dirs is OPT-IN (default () = bundled-only). The meta-repo's SSOT
    regen + lint + scaffold paths MUST stay bundled-only, so they get the default;
    only a consumer-discovery call site passes the resolved
    `cli._resources.overlay_template_dirs()` to include $COS_USER_TEMPLATES_DIR.
    (Defaulting it ON leaked community stacks into scaffold_manifest.json /
    dimension-registry.md via the regen scripts — pass-3 review.)
    """
    stacks: dict[str, StackProfile] = {}
    warnings: list[str] = []

    if templates_dir.is_dir():
        _scan_stack_dir(templates_dir, stacks, warnings, is_overlay=False)
    else:
        warnings.append(f"templates dir not found: {templates_dir}")
    for overlay in overlay_dirs:
        if overlay.is_dir():
            _scan_stack_dir(overlay, stacks, warnings, is_overlay=True)

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
