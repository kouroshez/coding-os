"""Render AggregatedWorld into concrete project artifacts.

Pure except for fragment file reads. Every renderer takes the world
(and maybe an adapter profile) and returns a string or dict ready to
be written.

The single most important contract: **NO literal markdown template
lives in this file**. Every piece of AGENTS.md or any other generated
doc comes from a fragment file declared in base.yaml or stack.yaml.
To add a new section, create a fragment and register it — do not
touch this module.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from jinja2.exceptions import TemplateError

from cli._data_types import AdapterProfile, AggregatedWorld, HookEntry

logger = logging.getLogger(__name__)


class RenderError(RuntimeError):
    """Raised when a fragment fails to render."""


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
    }


def render_agents_md(world: AggregatedWorld) -> str:
    """Render the full AGENTS.md by composing fragment templates.

    Sections are iterated in sorted order (already sorted by the
    aggregator). Each fragment is loaded from its owner's directory.
    Rendered pieces are joined with a single blank line between.
    """
    # Build one Jinja env per unique owner dir, cache by path.
    envs: dict[Path, Environment] = {}

    def env_for(owner: Path) -> Environment:
        if owner not in envs:
            envs[owner] = _make_env([owner])
        return envs[owner]

    context = _world_to_context(world)
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
        rendered_parts.append(text.rstrip())

    return "\n\n".join(rendered_parts) + "\n"


def _hook_to_settings_entry(hook: HookEntry) -> dict:
    """Convert a HookEntry into the shape .claude/settings.json expects."""
    return {
        "matcher": hook.matcher,
        "hooks": [{"type": "command", "command": hook.command}],
    }


def render_settings_json(
    world: AggregatedWorld, adapter: AdapterProfile
) -> dict:
    """Deep-merge adapter defaults with aggregated hooks.

    Returns {} if the adapter doesn't support settings.json — the caller
    is expected to skip writing the file in that case.
    """
    if not adapter.supports_settings_json:
        logger.debug(
            "adapter %s does not support settings.json, render_settings_json returns {}",
            adapter.id,
        )
        return {}

    result = deepcopy(adapter.default_settings)
    result.setdefault("hooks", {})
    hooks_section = result["hooks"]
    if not isinstance(hooks_section, dict):
        raise RenderError(
            f"adapter {adapter.id} default_settings.hooks must be a mapping"
        )

    # Group aggregated hooks by event.
    by_event: dict[str, list[HookEntry]] = {}
    for h in world.hooks:
        by_event.setdefault(h.event, []).append(h)

    for event, hook_list in by_event.items():
        hooks_section.setdefault(event, [])
        if not isinstance(hooks_section[event], list):
            raise RenderError(
                f"adapter {adapter.id} default_settings.hooks.{event} must be a list"
            )
        hooks_section[event].extend(_hook_to_settings_entry(h) for h in hook_list)

    return result


def render_makefile_targets(world: AggregatedWorld) -> str:
    """Produce a Makefile fragment with one target per aggregated entry.

    Designed to be written to <project>/.coding-os/Makefile.stacks and
    pulled into the project Makefile via `-include .coding-os/Makefile.stacks`.
    """
    if not world.makefile_targets:
        return "# No stack-contributed Makefile targets.\n"

    lines: list[str] = [
        "# Auto-generated by coding-os — do not edit by hand.",
        "# Regenerated every time `cos init` or `cos add-stack` runs.",
        "",
    ]
    phony = " ".join(t.name for t in world.makefile_targets)
    lines.append(f".PHONY: {phony}")
    lines.append("")
    for target in world.makefile_targets:
        if target.help:
            lines.append(f"{target.name}:  ## {target.help}")
        else:
            lines.append(f"{target.name}:")
        lines.append(f"\t{target.cmd}")
        lines.append("")
    return "\n".join(lines)


def render_dimension_registry(world: AggregatedWorld) -> str:
    """Aggregate dimension entries into a markdown doc grouped by stack."""
    lines: list[str] = [
        "# Dimension Registry",
        "",
        "Auto-generated from all installed stacks. Use during Classify",
        "phase to build your Read List.",
        "",
    ]
    if not world.dimensions:
        lines.append("_No dimensions contributed by any stack._")
        lines.append("")
        return "\n".join(lines)

    by_stack: dict[str, list] = {}
    for d in world.dimensions:
        by_stack.setdefault(d.stack_id, []).append(d)

    for stack_id in sorted(by_stack):
        lines.append(f"## {stack_id}")
        lines.append("")
        for dim in by_stack[stack_id]:
            files_fmt = ", ".join(f"`{f}`" for f in dim.read_files)
            lines.append(f"- **{dim.name}** ({dim.depth}) → {files_fmt}")
        lines.append("")
    return "\n".join(lines)


def render_skill_enforcement(world: AggregatedWorld) -> str:
    """Aggregate skill_enforcement entries into a markdown doc."""
    lines: list[str] = [
        "# Skill Enforcement",
        "",
        "Auto-generated. Before writing code matching any glob below,",
        "invoke the matching skill via the `Skill` tool.",
        "",
        "| Globs | Primary Skill | Secondary Skills | Stack |",
        "| --- | --- | --- | --- |",
    ]
    if not world.skill_enforcement:
        lines.append("| _none_ | _none_ | _none_ | _none_ |")
        lines.append("")
        return "\n".join(lines)

    for se in world.skill_enforcement:
        globs_fmt = ", ".join(f"`{g}`" for g in se.globs)
        secondary_fmt = ", ".join(se.secondary) if se.secondary else "—"
        lines.append(
            f"| {globs_fmt} | `{se.primary}` | {secondary_fmt} | {se.stack_id} |"
        )
    lines.append("")
    return "\n".join(lines)
