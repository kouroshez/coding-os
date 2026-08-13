"""Pure aggregation: (base + stacks + adapter) → AggregatedWorld.

No IO. No filesystem access. Deterministic output for a given input.
Fully testable as a plain function.

Merge rules (§2 of the plan):
    1. substitutions       shallow merge, later wins, conflict warned
    2. verify_rows         concat + dedupe by (glob, suites)
    3. routing_entries     concat + dedupe by string, order preserved
    4. ref_codes           concat + dedupe by code, diff path = warn
    5. makefile_targets    concat + dedupe by name, diff cmd = warn
    6. rules               concat, no dedupe
    7. agents_md_sections  concat, sort by (order, id)
    8. skills              union, first-occurrence order
    9. dimensions          concat + dedupe by (stack_id, name)
    10. skill_enforcement  concat + dedupe by (stack_id, globs, primary)
    11. hooks              concat; duplicate (event, command) = error
"""

from __future__ import annotations

from datetime import date


def today_iso() -> str:
    """Return today's date as ISO-8601. The single sanctioned way for
    production callers of aggregate() to obtain wall-clock date."""
    return date.today().isoformat()


from cli._data_types import (
    AdapterProfile,
    AgentsMdSection,
    AggregatedWorld,
    AnatomyEntry,
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


class AggregationError(ValueError):
    """Raised when aggregation hits an unrecoverable conflict (hook dup)."""


# Substrings that mark a base default as "obviously overridable" by any
# stack. Overriding a default is the happy path and should not emit a
# "conflict" warning — only real stack-vs-stack collisions should.
_BASE_DEFAULT_MARKERS = (
    "(none)",
    "(no ",
    "Polyglot",
    "Any code",
    "- See `docs/",
    "make verify`",  # the base fallback verify command
)


def _is_base_default(value: str) -> bool:
    if value == "":
        return True  # empty base placeholder (e.g. STACK_REF_CODES)
    return any(m in value for m in _BASE_DEFAULT_MARKERS)


# Keys whose final value is computed by _derive_substitutions as a JOIN of
# every contributing stack — a raw-merge collision on them is not a conflict
# (the later-wins intermediate is discarded), so no warning is emitted.
_JOINED_SUBSTITUTION_KEYS: frozenset[str] = frozenset(
    {
        "DOMAIN_ROUTES",
        "SKILL_ROUTES",
        "ENGINEERING_RULE_ROUTING",
        "TOOL_ROUTING_IMPL",
        "QUICK_ROUTING",
        "STACK_REF_CODES",
        "VERIFY_BACKEND_GLOB",
        "VERIFY_BACKEND_SUITES",
        "VERIFY_BACKEND",
        "VERIFY_FRONTEND_GLOB",
        "VERIFY_FRONTEND_SUITES",
        "VERIFY_FRONTEND",
        "VERIFY_MOBILE_GLOB",
        "VERIFY_MOBILE_SUITES",
        "VERIFY_MOBILE",
    }
)


def _merge_substitutions(
    base: dict[str, str],
    stacks: list[StackProfile],
) -> tuple[dict[str, str], list[str]]:
    """Shallow merge. Later value wins. NO auto-token resolution yet —
    that happens after derivation so derived values can also use tokens.

    Warnings are emitted only when two real values collide — overriding a
    base default is expected behaviour, not a conflict, and neither are
    collisions on keys whose final value is a derived join.
    """
    warnings: list[str] = []
    merged: dict[str, str] = dict(base)
    origin: dict[str, str] = dict.fromkeys(base, "base")
    for stack in stacks:
        for key, value in stack.substitutions.items():
            # Only warn on real conflicts, not base-default overrides.
            if (
                key in merged
                and merged[key] != value
                and key not in _JOINED_SUBSTITUTION_KEYS
                and (origin.get(key) != "base" or not _is_base_default(merged[key]))
            ):
                warnings.append(
                    f"substitution conflict on '{key}': "
                    f"'{merged[key]}' → '{value}' (stack {stack.id} wins)"
                )
            merged[key] = value
            origin[key] = stack.id
    return merged, warnings


def _resolve_auto_tokens(
    subs: dict[str, str],
    project_name: str,
    agent_id: str,
    today: str,
) -> dict[str, str]:
    """Replace ${auto:*} tokens in every substitution value.

    Runs AFTER both merge and derivation so derived values (STACK, etc.)
    can also contain auto tokens if a future stack declares them.

    `today` is always passed explicitly by the caller — aggregate() never
    reads the wall clock. This keeps the function pure and testable, and
    lets tests inject a deterministic value without env var tricks.
    """
    auto_values = {
        "${auto:project_name}": project_name,
        "${auto:today}": today,
        "${auto:agent}": agent_id,
    }
    out: dict[str, str] = {}
    for key, value in subs.items():
        for token, replacement in auto_values.items():
            if token in value:
                value = value.replace(token, replacement)
        out[key] = value
    return out


def _derive_substitutions(
    stacks: list[StackProfile],
    all_skills: tuple[str, ...],
) -> dict[str, str]:
    """Compute substitutions that depend on aggregated state.

    - STACK: joined stack labels (overrides base default when any stack present)
    - DOMAIN_ROUTES / SKILL_ROUTES / ENGINEERING_RULE_ROUTING / TOOL_ROUTING_IMPL:
      joined on " | " from each stack's substitution with the same key
    - QUICK_ROUTING / STACK_REF_CODES: joined on newlines (multi-line blocks)
    - INSTALLED_SKILLS: markdown-backtick list from aggregated skills
    """
    derived: dict[str, str] = {}

    if stacks:
        derived["STACK"] = " | ".join(s.label for s in stacks)

    # Join-on-" | " keys (single-line joins)
    for field_name in (
        "DOMAIN_ROUTES",
        "SKILL_ROUTES",
        "ENGINEERING_RULE_ROUTING",
        "TOOL_ROUTING_IMPL",
    ):
        parts = [s.substitutions[field_name] for s in stacks if field_name in s.substitutions]
        if parts:
            derived[field_name] = " | ".join(parts)

    # Join-on-newline keys (multi-line block joins)
    for field_name in ("QUICK_ROUTING", "STACK_REF_CODES"):
        parts = [s.substitutions[field_name] for s in stacks if field_name in s.substitutions]
        if parts:
            derived[field_name] = "\n".join(parts)

    # Verify-matrix keys render ONE row per category in AGENTS.md
    # (verification-matrix.md.tmpl). Plain merge is last-wins, which silently
    # drops a suite when two relocated same-category stacks coexist
    # (project-anatomy.md § Glob/verify propagation) — join with dedupe instead.
    for field_name in (
        "VERIFY_BACKEND_GLOB",
        "VERIFY_BACKEND_SUITES",
        "VERIFY_BACKEND",
        "VERIFY_FRONTEND_GLOB",
        "VERIFY_FRONTEND_SUITES",
        "VERIFY_FRONTEND",
        "VERIFY_MOBILE_GLOB",
        "VERIFY_MOBILE_SUITES",
        "VERIFY_MOBILE",
    ):
        parts = list(
            dict.fromkeys(
                s.substitutions[field_name] for s in stacks if field_name in s.substitutions
            )
        )
        if parts:
            derived[field_name] = " | ".join(parts)

    derived["INSTALLED_SKILLS"] = ", ".join(f"`{s}`" for s in all_skills)

    return derived


def _dedupe_verify(rows: list[VerifyRow]) -> tuple[VerifyRow, ...]:
    seen: set[tuple[str, str]] = set()
    out: list[VerifyRow] = []
    for row in rows:
        k = row.key()
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return tuple(out)


def _dedupe_strings(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)


def _dedupe_ref_codes(
    codes: list[RefCode],
) -> tuple[tuple[RefCode, ...], list[str]]:
    warnings: list[str] = []
    by_code: dict[str, RefCode] = {}
    order: list[str] = []
    for rc in codes:
        if rc.code in by_code:
            if by_code[rc.code].path != rc.path:
                warnings.append(
                    f"ref_code conflict on '{rc.code}': '{by_code[rc.code].path}' vs '{rc.path}'"
                )
            continue
        by_code[rc.code] = rc
        order.append(rc.code)
    return tuple(by_code[c] for c in order), warnings


def _dedupe_makefile_targets(
    targets: list[MakefileTarget],
) -> tuple[tuple[MakefileTarget, ...], list[str]]:
    warnings: list[str] = []
    by_name: dict[str, MakefileTarget] = {}
    order: list[str] = []
    for t in targets:
        if t.name in by_name:
            if by_name[t.name].cmd != t.cmd:
                warnings.append(
                    f"makefile target conflict on '{t.name}': '{by_name[t.name].cmd}' vs '{t.cmd}'"
                )
            continue
        by_name[t.name] = t
        order.append(t.name)
    return tuple(by_name[n] for n in order), warnings


def _sort_sections(
    sections: list[AgentsMdSection],
) -> tuple[AgentsMdSection, ...]:
    return tuple(sorted(sections, key=lambda s: (s.order, s.id)))


def _merge_skills(
    base_skills: tuple[str, ...], stack_skills_list: list[tuple[str, ...]]
) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for s in base_skills:
        if s not in seen:
            seen.add(s)
            out.append(s)
    for skills in stack_skills_list:
        for s in skills:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return tuple(out)


def _dedupe_dimensions(items: list[DimensionEntry]) -> tuple[DimensionEntry, ...]:
    seen: set[tuple[str, str]] = set()
    out: list[DimensionEntry] = []
    for d in items:
        k = (d.stack_id, d.name)
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return tuple(out)


def _dedupe_skill_enforcement(
    items: list[SkillEnforcementEntry],
) -> tuple[SkillEnforcementEntry, ...]:
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    out: list[SkillEnforcementEntry] = []
    for s in items:
        k = (s.stack_id, s.globs, s.primary)
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return tuple(out)


def _check_hook_conflicts(hooks: list[HookEntry]) -> None:
    seen: set[tuple[str, str]] = set()
    for h in hooks:
        k = (h.event, h.command)
        if k in seen:
            raise AggregationError(f"duplicate hook: event={h.event} command={h.command}")
        seen.add(k)


def aggregate(
    base: BaseProfile,
    stacks: list[StackProfile],
    adapter: AdapterProfile,
    project_name: str,
    *,
    today: str,
) -> AggregatedWorld:
    """Merge base + stacks + adapter into a single deterministic world.

    `today` is an ISO-8601 date string the caller supplies. This keeps
    aggregate() a pure function with no hidden wall-clock dependency —
    tests can pass any fixed date, production callers pass
    `date.today().isoformat()`.
    """
    all_conflicts: list[str] = []

    # 1. substitutions (merge only; auto-tokens resolved after derivation)
    subs, warn = _merge_substitutions(base.substitutions, stacks)
    all_conflicts.extend(warn)

    # 2. verify rows
    verify = _dedupe_verify(list(base.verify) + [row for s in stacks for row in s.verify])

    # 3. routing entries
    routing = _dedupe_strings(
        list(base.routing_entries) + [r for s in stacks for r in s.routing_entries]
    )

    # 4. ref codes
    ref_codes, warn = _dedupe_ref_codes(
        list(base.ref_codes) + [rc for s in stacks for rc in s.ref_codes]
    )
    all_conflicts.extend(warn)

    # 5. makefile targets
    makefile_targets, warn = _dedupe_makefile_targets(
        list(base.makefile_targets) + [t for s in stacks for t in s.makefile_targets]
    )
    all_conflicts.extend(warn)

    # 6. rules — concat, no dedupe
    rules: tuple[RuleEntry, ...] = tuple(list(base.rules) + [r for s in stacks for r in s.rules])

    # 7. agents_md_sections
    sections = _sort_sections(
        list(base.agents_md_sections) + [sec for s in stacks for sec in s.agents_md_sections]
    )

    # 8. skills
    skills = _merge_skills(base.skills, [s.skills for s in stacks])

    # Derived substitutions that depend on the aggregated skills/stacks.
    derived = _derive_substitutions(stacks, skills)
    for key, value in derived.items():
        subs[key] = value

    # Resolve ${auto:*} tokens AFTER both merge and derivation so derived
    # values can also contain auto references.
    subs = _resolve_auto_tokens(subs, project_name, adapter.id, today)

    # 9. dimensions
    dimensions = _dedupe_dimensions(
        list(base.dimensions) + [d for s in stacks for d in s.dimensions]
    )

    # 10. skill_enforcement
    skill_enforcement = _dedupe_skill_enforcement(
        list(base.skill_enforcement) + [se for s in stacks for se in s.skill_enforcement]
    )

    # 11. hooks — concat; dup = error
    hooks = list(base.hooks) + [h for s in stacks for h in s.hooks]
    _check_hook_conflicts(hooks)

    # Anatomy map — one entry per installed stack that declares a root.
    # `stacks` are already relocated by the world builder, so structure.root
    # is the actual on-disk root (multi-backend → src/services/<id>/).
    anatomy = tuple(
        AnatomyEntry(
            stack_id=s.id,
            label=s.label,
            category=s.category,
            root=s.structure["root"],
            notes=s.structure.get("notes", ""),
        )
        for s in stacks
        if s.structure.get("root")
    )

    return AggregatedWorld(
        project_name=project_name,
        agent_id=adapter.id,
        stack_ids=tuple(s.id for s in stacks),
        substitutions=subs,
        skills=skills,
        verify_rows=verify,
        routing_entries=routing,
        ref_codes=ref_codes,
        makefile_targets=makefile_targets,
        rules=rules,
        dimensions=dimensions,
        skill_enforcement=skill_enforcement,
        agents_md_sections=sections,
        hooks=tuple(hooks),
        conflicts=tuple(all_conflicts),
        anatomy=anatomy,
    )
