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
import re
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
        "anatomy": world.anatomy,
    }


def _modules_context(active_modules: dict[str, bool] | None) -> dict[str, bool]:
    """Full {module_id: enabled} map for Jinja — every registry module gets a
    key so StrictUndefined never fires inside a fragment. None → all enabled
    (backward compatible default for regen scripts and golden fixtures)."""
    from cli.subsystems import load_subsystems

    base = {module_id: True for module_id in load_subsystems()}
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


def _hook_to_settings_entry(hook: HookEntry) -> dict:
    """Convert a HookEntry into the shape .claude/settings.json expects."""
    return {
        "matcher": hook.matcher,
        "hooks": [{"type": "command", "command": hook.command}],
    }


def render_settings_json(world: AggregatedWorld, adapter: AdapterProfile) -> dict:
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
        raise RenderError(f"adapter {adapter.id} default_settings.hooks must be a mapping")

    # Group aggregated hooks by event.
    by_event: dict[str, list[HookEntry]] = {}
    for h in world.hooks:
        by_event.setdefault(h.event, []).append(h)

    for event, hook_list in by_event.items():
        hooks_section.setdefault(event, [])
        if not isinstance(hooks_section[event], list):
            raise RenderError(f"adapter {adapter.id} default_settings.hooks.{event} must be a list")
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


# File extension a verify-row glob ends with → language. Languages are the gate
# for which toolchain CI installs; the row owns one stack root, hence one match.
_EXT_LANGUAGE: dict[str, str] = {
    "py": "python",
    "ts": "typescript",
    "tsx": "typescript",
    "js": "typescript",
    "jsx": "typescript",
    "go": "go",
    "php": "php",
    "rs": "rust",
    "rb": "ruby",
    "java": "java",
    "kt": "java",
    "cs": "csharp",
    "dart": "dart",
}

# Language → GitHub Actions toolchain setup step(s). Pinned to the runtime only,
# never the lint/test tools — those stay in `make`, so this never rots when a
# framework version moves. A language with no entry runs make against whatever
# the runner preinstalls (best effort).
_CI_LANGUAGE_SETUP: dict[str, tuple[str, ...]] = {
    "python": (
        "uses: actions/setup-python@v5",
        "with:",
        '  python-version: "3.12"',
    ),
    "typescript": (
        "uses: actions/setup-node@v4",
        "with:",
        '  node-version: "20"',
    ),
    "go": (
        "uses: actions/setup-go@v5",
        "with:",
        '  go-version: "stable"',
    ),
    "php": (
        "uses: shivammathur/setup-php@v2",
        "with:",
        '  php-version: "8.2"',
    ),
    "rust": ("uses: dtolnay/rust-toolchain@stable",),
    "ruby": (
        "uses: ruby/setup-ruby@v1",
        "with:",
        '  ruby-version: "3.3"',
    ),
    "java": (
        "uses: actions/setup-java@v4",
        "with:",
        '  distribution: "temurin"',
        '  java-version: "21"',
    ),
    "csharp": (
        "uses: actions/setup-dotnet@v4",
        "with:",
        '  dotnet-version: "8.0"',
    ),
    "dart": ("uses: dart-lang/setup-dart@v1",),
}

# Language → per-stack-root dependency install. Mirrors the bootable manifests
# (TASK-605..608): pyproject `[test]` extras, package.json, go.mod, composer.json.
_CI_LANGUAGE_INSTALL: dict[str, str] = {
    "python": "pip install -e '.[test]'",
    "typescript": "npm install",
    "go": "go mod download",
    "php": "composer install",
}


def _language_for_glob(glob: str) -> str:
    tail = glob.rsplit("/", 1)[-1]
    if "." not in tail:
        return ""
    for ext in re.findall(r"[A-Za-z0-9]+", tail.split(".", 1)[-1]):
        if ext in _EXT_LANGUAGE:
            return _EXT_LANGUAGE[ext]
    return ""


def render_ci_workflow(world: AggregatedWorld) -> str:
    """Emit a single .github/workflows/ci.yml — the structural twin of
    render_makefile_targets.

    Consumer-owned (written once at init, not a live symlink). One matrix leg
    per language, each running that language's generated make targets, so the
    body delegates to `make` and never rots with tool versions; re-rendering
    after a stack is added picks up its targets automatically. macOS is kept
    off the per-push path — those runners bill at 10x.
    """
    runnable = {t.name for t in world.makefile_targets}
    targets_by_language: dict[str, list[str]] = {}
    roots_by_language: dict[str, list[str]] = {}
    for row in world.verify_rows:
        language = _language_for_glob(row.glob)
        if not language:
            continue
        for suite in row.suites.split("+"):
            name = suite.strip()
            if name in runnable and name not in targets_by_language.setdefault(language, []):
                targets_by_language.setdefault(language, []).append(name)
        root = row.glob.split("/**", 1)[0].rstrip("/")
        if root and root not in roots_by_language.setdefault(language, []):
            roots_by_language[language].append(root)

    languages = [lang for lang in targets_by_language if targets_by_language[lang]]
    if not languages:
        return ""

    lines: list[str] = [
        "# Auto-generated by coding-os `cos init` — consumer-owned (edit freely; not a symlink).",
        "# Body delegates to the generated make targets so it never rots with tool",
        "# versions; adding a stack re-renders this with the new targets.",
        "name: CI",
        "on:",
        "  push:",
        "    branches: [main]",
        '    paths-ignore: ["docs/tasks/**"]',
        "  pull_request:",
        "    branches: [main]",
        "  workflow_dispatch:",
        "concurrency:",
        "  group: ci-${{ github.workflow }}-${{ github.ref }}",
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
        "permissions:",
        "  contents: read",
        "jobs:",
        "  verify:",
        "    name: verify (${{ matrix.language }})",
        # macOS runners bill at 10x — never on the per-push path (nightly elsewhere if needed).
        "    runs-on: ubuntu-latest",
        "    strategy:",
        "      fail-fast: false",
        "      matrix:",
        "        include:",
    ]
    for lang in languages:
        lines.append(f"          - language: {lang}")
        lines.append(f'            targets: "{" ".join(targets_by_language[lang])}"')
    lines.append("    steps:")
    lines.append("      - uses: actions/checkout@v4")
    for lang in languages:
        guard = f"        if: matrix.language == '{lang}'"
        for index, step_line in enumerate(_CI_LANGUAGE_SETUP.get(lang, ())):
            prefix = "      - " if index == 0 else "        "
            lines.append(prefix + step_line)
            if index == 0:
                lines.append(guard)
        install = _CI_LANGUAGE_INSTALL.get(lang)
        if install:
            lines.append(f"      - name: deps ({lang})")
            lines.append(guard)
            lines.append("        run: |")
            for root in roots_by_language.get(lang, []):
                lines.append(f"          (cd {root} && {install})")
    lines.append("      - name: verify")
    lines.append("        run: make ${{ matrix.targets }}")
    return "\n".join(lines) + "\n"


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
        lines.append(f"| {globs_fmt} | `{se.primary}` | {secondary_fmt} | {se.stack_id} |")
    lines.append("")
    return "\n".join(lines)
