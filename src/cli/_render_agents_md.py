"""Compose AGENTS.md from the fragment templates each stack contributes.

The only Jinja2 in the renderer lives here, and with it the module-gating rules
that decide which fragments and skills survive into the rendered doc. Nothing
else needs a template environment, so nothing else carries this import.

The single most important contract still holds: **NO literal markdown template
lives in this file**. Every section comes from a fragment declared in base.yaml
or stack.yaml.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from jinja2.exceptions import TemplateError

from cli._data_types import AggregatedWorld
from cli._render_errors import RenderError

logger = logging.getLogger(__name__)


def _make_env(search_paths: list[Path]) -> Environment:
    """Build a Jinja2 environment that searches multiple fragment roots.

    Autoescape is OFF — we render Markdown, not HTML. StrictUndefined
    is ON — any unbound variable in a fragment is a loud error (D22).
    """
    return Environment(
        loader=FileSystemLoader([str(p) for p in search_paths]),
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=StrictUndefined,
    )


def _world_to_context(world: AggregatedWorld) -> dict:
    """Expose the world as a plain dict so Jinja can access all fields."""
    return {
        "project_name": world.project_name,
        "agent_id": world.agent_id,
        "stack_ids": world.stack_ids,
        "substitutions": world.substitutions,
        "skills": world.skills,
        "verify_rows": world.verify_rows,
        "routing_entries": world.routing_entries,
        "ref_codes": world.ref_codes,
        "makefile_targets": world.makefile_targets,
        "rules": world.rules,
        "dimensions": world.dimensions,
        "skill_enforcement": world.skill_enforcement,
        "agents_md_sections": world.agents_md_sections,
        "hooks": world.hooks,
        "conflicts": world.conflicts,
        "anatomy": world.anatomy,
    }


def _modules_context(active_modules: dict[str, bool] | None) -> dict[str, bool]:
    """Full {module_id: enabled} map for Jinja — every registry module gets a
    key so StrictUndefined never fires inside a fragment. None → all enabled
    (backward compatible default for regen scripts and golden fixtures)."""
    from cli.subsystems import load_subsystems

    base = dict.fromkeys(load_subsystems(), True)
    if active_modules:
        base.update({k: bool(v) for k, v in active_modules.items() if k in base})
    return base


def _disabled_module_skills(modules: dict[str, bool]) -> set[str]:
    """Skills owned ONLY by disabled modules — ref-counted so a skill an
    enabled module also owns survives (parity with the on-disk skill cascade in
    skill_commands.planned_skill_unlinks)."""
    from cli.subsystems import load_subsystems

    registry = load_subsystems()
    enabled_owned = {s for mid, m in registry.items() if modules.get(mid, True) for s in m.skills}
    disabled_owned = {
        s for mid, m in registry.items() if not modules.get(mid, True) for s in m.skills
    }
    return disabled_owned - enabled_owned


def _gate_installed_skills(context: dict, world: AggregatedWorld, modules: dict[str, bool]) -> None:
    """Drop a disabled module's owned skills from the rendered `## Skills` list
    (INSTALLED_SKILLS) so a gated module leaves no orphaned skill mention (audit
    D2-2). No-op when nothing is disabled, so the all-on render is byte-identical."""
    dropped = _disabled_module_skills(modules)
    if not dropped:
        return
    kept = [s for s in world.skills if s not in dropped]
    subs = dict(context.get("substitutions") or {})
    subs["INSTALLED_SKILLS"] = ", ".join(f"`{s}`" for s in kept)
    context["substitutions"] = subs


def render_agents_md(world: AggregatedWorld, active_modules: dict[str, bool] | None = None) -> str:
    """Render the full AGENTS.md by composing fragment templates.

    Sections are iterated in sorted order (already sorted by the
    aggregator). Each fragment is loaded from its owner's directory.
    Rendered pieces are joined with a single blank line between.

    Conditional rendering: fragments receive a `modules` map for inline
    `{% if modules.<id> %}` blocks; a fragment that renders empty once its
    gated blocks drop out is skipped wholesale.
    """
    # Build one Jinja env per unique owner dir, cache by path.
    envs: dict[Path, Environment] = {}

    def env_for(owner: Path) -> Environment:
        if owner not in envs:
            envs[owner] = _make_env([owner])
        return envs[owner]

    modules = _modules_context(active_modules)
    context = {**_world_to_context(world), "modules": modules}
    _gate_installed_skills(context, world, modules)
    rendered_parts: list[str] = []
    for section in world.agents_md_sections:
        env = env_for(section.owner_dir)
        try:
            template = env.get_template(section.template)
        except TemplateError as exc:
            raise RenderError(
                f"fragment '{section.template}' in {section.owner_dir} failed to load: {exc}"
            ) from exc
        try:
            text = template.render(**context)
        except TemplateError as exc:
            raise RenderError(
                f"fragment '{section.template}' (section {section.id}) failed to render: {exc}"
            ) from exc
        part = text.rstrip()
        if part:  # a fully module-gated fragment renders empty — skip it
            rendered_parts.append(part)

    return "\n\n".join(rendered_parts) + "\n"
