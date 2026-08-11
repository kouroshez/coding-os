"""Language grouping and the service-root relocation rules for multi-stack projects."""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from cli._data_types import MakefileTarget, StackProfile, VerifyRow
from cli._stack_parsers import StackLoadResult

logger = logging.getLogger(__name__)


def group_stacks_by_language(
    stacks: dict[str, StackProfile],
) -> dict[str, list[StackProfile]]:
    """Language → stacks (plain stack first, then alphabetical) for discovery."""
    groups: dict[str, list[StackProfile]] = {}
    for profile in stacks.values():
        groups.setdefault(profile.language or "other", []).append(profile)
    for _language, members in groups.items():
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


def _roots_collide(root_a: str, lang_a: str, root_b: str, lang_b: str) -> bool:
    if root_a == root_b:
        return True  # two stacks rooted at the same path always collide
    # A nested root only collides when the two stacks own the SAME file types
    # (same language): a TS language-layer at `src` legitimately CONTAINS a Go
    # backend at `src/backend` (.ts vs .go never overlap), but it collides with
    # a Next.js app at `src/frontend` — both then own `src/frontend/**/*.ts`.
    nested = root_a.startswith(root_b + "/") or root_b.startswith(root_a + "/")
    return nested and lang_a == lang_b


def service_relocations(
    stacks: dict[str, StackProfile] | StackLoadResult,
    templates: tuple[str, ...] | list[str],
) -> dict[str, str]:
    """stack-id → src/services/<id> for selected stacks whose structure.root collides.

    Anatomy contract (project-anatomy.md § Multi-backend relocation rule):
    single-owner roots are untouched; every collision participant relocates. A
    collision is roots that EQUAL, or NEST while sharing a language (so the inner
    and outer stack would own the same files) — an ad-hoc typescript-plain over
    nextjs init (`src` containing `src/frontend`) is the motivating case."""
    entries: list[tuple[str, str, str]] = []
    for name in templates:
        # StackLoadResult is dict-like via __contains__/__getitem__ but has no .get().
        profile = stacks[name] if name in stacks else None  # noqa: SIM401
        if profile is None:
            continue
        root = (profile.structure or {}).get("root")
        if root:
            entries.append((name, root.rstrip("/"), profile.language or ""))
    colliding: dict[str, None] = {}
    for index, (id_a, root_a, lang_a) in enumerate(entries):
        for id_b, root_b, lang_b in entries[index + 1 :]:
            if _roots_collide(root_a, lang_a, root_b, lang_b):
                colliding[id_a] = None
                colliding[id_b] = None
    return {stack_id: f"src/services/{stack_id}" for stack_id in colliding}


def relocate_profile(profile: StackProfile, new_root: str) -> StackProfile:
    """Service-scoped copy of a profile (project-anatomy.md § Glob/verify propagation).

    Path-shaped fields get a prefix remap from the declared structure.root;
    command/substitution text gets a boundary-aware root swap; makefile target
    names — and the suites/substitution text referencing them — gain a
    -<stack-id> suffix, because two relocated stacks both declare e.g.
    lint-backend and aggregate() dedupes by name (one suite silently lost)."""
    declared = (profile.structure or {}).get("root", "").rstrip("/")
    if not declared or declared == new_root.rstrip("/"):
        return profile
    new_root = new_root.rstrip("/")

    root_pattern = re.compile(re.escape(declared) + r"(?![\w-])")

    def _swap_text(text: str) -> str:
        return root_pattern.sub(new_root, text)

    def _swap_paths(items: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            new_root + item[len(declared) :]
            if item == declared or item.startswith(declared + "/")
            else item
            for item in items
        )

    renames = {t.name: f"{t.name}-{profile.id}" for t in profile.makefile_targets}
    name_pattern = (
        re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in renames) + r")(?![\w-])")
        if renames
        else None
    )

    def _swap_names(text: str) -> str:
        if name_pattern is None:
            return text
        return name_pattern.sub(lambda m: renames[m.group(1)], text)

    structure = {**profile.structure, "root": new_root}
    if "tree" in structure:
        structure["tree"] = _swap_text(structure["tree"])

    return replace(
        profile,
        substitutions={k: _swap_text(_swap_names(v)) for k, v in profile.substitutions.items()},
        verify=tuple(
            VerifyRow(glob=_swap_text(r.glob), suites=_swap_names(r.suites), cmd=_swap_text(r.cmd))
            for r in profile.verify
        ),
        routing_entries=tuple(_swap_text(_swap_names(e)) for e in profile.routing_entries),
        makefile_targets=tuple(
            MakefileTarget(name=renames[t.name], cmd=_swap_text(t.cmd), help=t.help)
            for t in profile.makefile_targets
        ),
        rules=tuple(replace(r, globs=_swap_paths(r.globs)) for r in profile.rules),
        dimensions=tuple(
            replace(d, read_files=_swap_paths(d.read_files)) for d in profile.dimensions
        ),
        skill_enforcement=tuple(
            replace(se, globs=_swap_paths(se.globs)) for se in profile.skill_enforcement
        ),
        structure=structure,
    )


def resolve_relocated_profiles(
    stacks: dict[str, StackProfile] | StackLoadResult,
    templates: tuple[str, ...] | list[str],
) -> list[StackProfile]:
    """Selected profiles in template order, with colliding roots relocated.

    The shared pre-aggregate step for both world builders (cli.main._build_world,
    cli.update._aggregate_world) — meta-repo regen (regen_rules.py) intentionally
    bypasses it, see project-anatomy.md § invariants."""
    relocations = service_relocations(stacks, templates)
    profiles: list[StackProfile] = []
    for name in templates:
        if name not in stacks:
            continue
        profile = stacks[name]
        new_root = relocations.get(name)
        profiles.append(relocate_profile(profile, new_root) if new_root else profile)
    return profiles
