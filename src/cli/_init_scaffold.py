"""Scaffold materialisation for `cos init` — templates, overlays, doc conditions.

Everything here answers one question: given a resolved world (stacks, adapter,
modules), what files land in the consumer project and where. It depends only on
_init_registries, so the phase driver and the preview can both build on it.
"""

from __future__ import annotations

import filecmp
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import click

from cli._init_boundaries import _aggregate_scaffold_boundaries  # noqa: F401
from cli._init_registries import (
    CORE_DIR,
    STATE_DIR,
    TEMPLATES_DIR,
    _get_adapter_registry,
    _get_stack_registry,
)
from cli._resources import data_root, templates_dir
from cli.config_composer import COMPOSED_FILENAMES
from cli.stack_registry import service_relocations


def _link_stack_skills(
    agent: str,
    templates: tuple[str, ...],
    project_dir: Path,
) -> None:
    """Symlink each applied stack's skills into the agent's skills_dir.

    No-op for adapters whose skills_dir is null (e.g. Codex). Delegates the
    filesystem work to src/core/scripts/link-stack-skills.sh so the same logic
    is callable from Make targets / cos update.
    """
    registry = _get_adapter_registry()
    if agent not in registry:
        return
    skills_dir = registry[agent].skills_dir
    if not skills_dir:
        return
    linker = CORE_DIR / "scripts" / "link-stack-skills.sh"
    if not linker.exists():
        click.echo(f"  WARN: stack-skill linker missing: {linker}", err=True)
        return
    agent_skills_abs = str(project_dir / skills_dir)
    result = subprocess.run(
        ["bash", str(linker), agent_skills_abs, str(data_root()), *templates],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(
            f"  WARN: stack-skill linking failed:\n{result.stderr}",
            err=True,
        )
        return
    linked = []
    for t in templates:
        stack_skills = templates_dir(t, "skills")
        if stack_skills.exists():
            linked.extend(sorted(p.name for p in stack_skills.iterdir() if p.is_dir()))
    if linked:
        click.echo(f"  Linked stack skills: {', '.join(linked)}")

    # Community-overlay stacks live outside the bundled tree the shell linker
    # scans (data_root), so link their skills here from the resolved source_dir
    # . Only fires for a stack whose source_dir is NOT under TEMPLATES_DIR.
    stack_registry = _get_stack_registry()
    bundled_root = TEMPLATES_DIR.resolve()
    community: list[str] = []
    for t in templates:
        if t not in stack_registry:
            continue
        source_dir = stack_registry[t].source_dir.resolve()
        try:
            source_dir.relative_to(bundled_root)
            continue  # bundled — already linked by the shell
        except ValueError:
            pass  # community overlay stack
        skills_src = source_dir / "skills"
        if not skills_src.is_dir():
            continue
        for skill_dir in sorted(p for p in skills_src.iterdir() if p.is_dir()):
            src_md = skill_dir / "SKILL.md"
            dest = project_dir / skills_dir / skill_dir.name / "SKILL.md"
            if not src_md.is_file() or dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.symlink_to(src_md)
            community.append(skill_dir.name)
    if community:
        click.echo(f"  Linked community stack skills: {', '.join(community)}")


def _run_adapter_install(agent: str, project_dir: Path) -> None:
    """Run the adapter's declared install script.

    Uses adapter.yaml::install_script so a new adapter is pure data — no
    hardcoded path assumption.
    """
    registry = _get_adapter_registry()
    if agent not in registry:
        click.echo(
            f"  ERROR: Unknown adapter '{agent}' — available: {sorted(registry.keys())}",
            err=True,
        )
        sys.exit(1)
    install_script = registry[agent].install_script
    if not install_script.exists():
        click.echo(
            f"  ERROR: Adapter install script not found: {install_script}",
            err=True,
        )
        sys.exit(1)

    result = subprocess.run(
        ["bash", str(install_script)],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        click.echo(result.stdout)
    if result.returncode != 0:
        click.echo(f"  ERROR: Adapter install failed:\n{result.stderr}", err=True)
        sys.exit(1)


def _apply_template(
    template_name: str,
    project_dir: Path,
    agent: str | None = None,
) -> None:
    """Apply a stack template to the project.

    1. Copies `src/templates/<name>/{rules,skills,playbooks,hooks}/` to
       `<project>/.coding-os/templates/<name>/…` for browsing.
    2. If `agent` is provided and that adapter supports path-scoped rules
       (`adapter.rules_dir` != null), also copies every
       `src/templates/<name>/rules/*.md` into the adapter's rules dir with a
       `<stack>-<filename>` prefix so multiple stacks coexist.
    """
    stack_registry = _get_stack_registry()
    if template_name not in stack_registry:
        click.echo(
            f"  WARN: Template '{template_name}' not in registry "
            f"(available: {sorted(stack_registry.keys())})",
            err=True,
        )
        return
    stack_profile = stack_registry[template_name]
    template_dir = stack_profile.source_dir

    # 1. Mirror every subdir into .coding-os/templates/<name>/
    for subdir in ("rules", "skills", "playbooks", "hooks"):
        src = template_dir / subdir
        if src.exists():
            dest = project_dir / STATE_DIR / "src" / "templates" / template_name / subdir
            dest.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                if item.is_file():
                    shutil.copy2(item, dest / item.name)
                elif item.is_dir():
                    shutil.copytree(item, dest / item.name, dirs_exist_ok=True)

    # 2. Copy path-scoped rules into the adapter's rules_dir (if supported).
    if agent is not None:
        adapters = _get_adapter_registry()
        if agent in adapters:
            adapter_profile = adapters[agent]
            if adapter_profile.supports_rules and adapter_profile.rules_dir:
                rules_src = template_dir / "rules"
                if rules_src.exists():
                    rules_dest = project_dir / adapter_profile.rules_dir
                    rules_dest.mkdir(parents=True, exist_ok=True)
                    for rule_file in sorted(rules_src.glob("*.md")):
                        # Prefix with stack id to avoid collisions between stacks.
                        out = rules_dest / f"{template_name}-{rule_file.name}"
                        shutil.copy2(rule_file, out)
            elif not adapter_profile.supports_rules:
                click.echo(
                    f"  INFO: adapter '{agent}' does not support path-scoped "
                    f"rules — skipping rules copy for '{template_name}'",
                )

    click.echo(f"  Template '{template_name}' applied.")


def refresh_stack_rules(
    template_name: str,
    project_dir: Path,
    agents: Sequence[str | None],
    *,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    """Re-copy stack rules the user never touched; return (refreshed, kept).

    Core rules are symlinks and reach every project the moment they change; stack
    rules are copies, so a correction to `src/templates/<stack>/rules/` reached no
    existing install at all. The install-time mirror under `.coding-os/src/templates/`
    is a byte-exact snapshot of what was copied — the baseline that separates an
    untouched file from an edited one without inventing a hash sidecar.

    Every adapter is decided against the SAME mirror and the mirror moves once, at
    the end: advancing it inside a per-adapter pass refreshed the first adapter and
    left every later one reading its own untouched copy as a user edit, forever.
    """
    stack_registry = _get_stack_registry()
    if template_name not in stack_registry:
        return [], []
    source_dir = stack_registry[template_name].source_dir / "rules"
    if not source_dir.is_dir():
        return [], []
    mirror_dir = project_dir / STATE_DIR / "src" / "templates" / template_name / "rules"

    refreshed: list[str] = []
    kept: list[str] = []
    advanced: set[Path] = set()
    for rules_dir in _rules_dirs_for(project_dir, agents):
        for source in sorted(source_dir.glob("*.md")):
            installed = rules_dir / f"{template_name}-{source.name}"
            mirror = mirror_dir / source.name
            if not installed.is_file():
                continue
            # Already current: nothing to refresh and nobody to warn. This test
            # comes first because the mirror can be older than both, and an
            # install predating it would otherwise have every untouched rule
            # reported back to its owner as "you edited this".
            if filecmp.cmp(installed, source, shallow=False):
                continue
            if not mirror.is_file():
                kept.append(f"{installed.name} (no baseline to compare against)")
                continue
            if not filecmp.cmp(installed, mirror, shallow=False):
                kept.append(installed.name)
                continue
            if not dry_run:
                shutil.copy2(source, installed)
            advanced.add(mirror)
            refreshed.append(installed.name)

    if not dry_run:
        for mirror in advanced:
            shutil.copy2(source_dir / mirror.name, mirror)
    return refreshed, kept


def _rules_dirs_for(project_dir: Path, agents: Sequence[str | None]) -> list[Path]:
    adapters = _get_adapter_registry()
    dirs: list[Path] = []
    for agent in agents:
        if agent is None:
            continue
        profile = adapters.get(agent)
        if profile is None or not profile.supports_rules or not profile.rules_dir:
            continue
        dirs.append(project_dir / profile.rules_dir)
    return dirs


def _resolve_placeholders(text: str, substitutions: dict[str, str]) -> str:
    """Replace `{{KEY}}` placeholders. Unknown keys are left intact for later overlay."""
    result = text
    for key, value in substitutions.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


_DOC_MODULE_TAG_RE = re.compile(r"\s*\|\s*module:([a-z][a-z0-9_-]*)")
_DOC_IF_RE = re.compile(r"^<!--\s*if-(stack|module):([a-z0-9_,-]+)\s*-->\s*$")
_DOC_ENDIF_RE = re.compile(r"^<!--\s*end-if\s*-->\s*$")


def _apply_doc_conditions(
    text: str, disabled_modules: set[str], active_stacks: set[str]
) -> tuple[bool, str]:
    """(skip_file, transformed_text) — see the marker contract above."""
    lines = text.split("\n")
    if lines:
        tag = _DOC_MODULE_TAG_RE.search(lines[0])
        if tag and lines[0].lstrip().startswith("<!--"):
            if tag.group(1) in disabled_modules:
                return True, ""
            lines[0] = _DOC_MODULE_TAG_RE.sub("", lines[0], count=1)

    out: list[str] = []
    keeping = True
    in_block = False
    for line in lines:
        opener = _DOC_IF_RE.match(line)
        if opener and not in_block:
            in_block = True
            kind, raw_ids = opener.group(1), opener.group(2)
            wanted = {x for x in raw_ids.split(",") if x}
            if kind == "stack":
                keeping = bool(wanted & active_stacks)
            else:
                keeping = not (wanted & disabled_modules)
            continue
        if _DOC_ENDIF_RE.match(line) and in_block:
            in_block = False
            keeping = True
            continue
        if keeping:
            out.append(line)
    return False, "\n".join(out)


def module_scaffold_doc_rels(templates: tuple[str, ...], module_id: str) -> list[str]:
    """Consumer-relative paths of scaffold `.md` docs tagged `| module:<module_id>`.

    Reuses the source-root + relocation mapping of the scaffold overlay so the
    result matches what init composed. Shared by the toggle doc-sync (prune /
    restore, TASK-813) and cos doctor's modules.doc_drift backstop — the consumer
    copy has its tag STRIPPED at init, so drift/prune must map via the tagged
    SOURCE, never the untagged destination."""
    registry = _get_stack_registry()
    relocations = _service_relocations(templates)
    sources: list[tuple[Path, str | None]] = [(TEMPLATES_DIR / "_base" / "scaffold", None)]
    for name in templates:
        stack_root = registry[name].source_dir if name in registry else TEMPLATES_DIR / name
        candidate = stack_root / "scaffold"
        if candidate.exists():
            sources.append((candidate, name))
    rels: set[str] = set()
    for src_root, stack_id in sources:
        if not src_root.exists():
            continue
        relocated_root = relocations.get(stack_id) if stack_id else None
        declared_root = (
            (registry[stack_id].structure or {}).get("root", "").rstrip("/")
            if stack_id and stack_id in registry
            else ""
        )
        for src_file in src_root.rglob("*.md"):
            if not src_file.is_file():
                continue
            try:
                first = src_file.read_text(encoding="utf-8").split("\n", 1)[0]
            except OSError:
                continue
            if not first.lstrip().startswith("<!--"):
                continue
            tag = _DOC_MODULE_TAG_RE.search(first)
            if not (tag and tag.group(1) == module_id):
                continue
            rel = src_file.relative_to(src_root)
            if relocated_root and declared_root and str(rel).startswith(declared_root + "/"):
                rel = Path(relocated_root) / str(rel)[len(declared_root) + 1 :]
            rels.add(str(rel))
    return sorted(rels)


def _service_relocations(templates: tuple[str, ...]) -> dict[str, str]:
    """stack-id → relocated root for stacks whose structure.root collides.

    Thin wrapper over the SSOT in cli.stack_registry (shared with
    cli.update._aggregate_world); see project-anatomy.md.
    """
    return service_relocations(_get_stack_registry(), templates)


def _overlay_scaffold(
    project: Path,
    templates: tuple[str, ...],
    substitutions: dict[str, str],
) -> int:
    """Copy `_base/scaffold/` then each template's `scaffold/` into `project/`.

    Existing project files are NEVER overwritten (idempotent init).
    Markdown files have their `{{KEY}}` placeholders resolved.

    Returns: count of files copied.
    """
    # Source roots in overlay order: _base first, then each template overlay.
    # Each entry: (scaffold dir, owning stack id or None for _base). A community
    # stack's scaffold lives at its resolved source_dir, not the bundled tree.
    registry = _get_stack_registry()
    sources: list[tuple[Path, str | None]] = [(TEMPLATES_DIR / "_base" / "scaffold", None)]
    for name in templates:
        stack_root = registry[name].source_dir if name in registry else TEMPLATES_DIR / name
        candidate = stack_root / "scaffold"
        if candidate.exists():
            sources.append((candidate, name))

    # Per-language toolchain config (ruff/pytest, eslint/prettier/vitest) lives once
    # under _base/lang/<language>/, selected by each active stack's declared language.
    # Overlaid LAST so a stack's own scaffold config wins the idempotent first-write.
    seen_languages: set[str] = set()
    for name in templates:
        language = registry[name].language if name in registry else ""
        if not language or language in seen_languages:
            continue
        seen_languages.add(language)
        lang_dir = TEMPLATES_DIR / "_base" / "lang" / language
        if lang_dir.exists():
            sources.append((lang_dir, None))

    relocations = _service_relocations(templates)

    from cli.subsystems import module_state

    disabled_modules = {
        module_id for module_id, enabled in module_state(project).items() if not enabled
    }
    active_stacks = set(templates)

    copied = 0
    for src_root, stack_id in sources:
        if not src_root.exists():
            continue
        relocated_root = relocations.get(stack_id) if stack_id else None
        declared_root = (
            (registry[stack_id].structure or {}).get("root", "").rstrip("/")
            if stack_id and stack_id in registry
            else ""
        )
        for src_file in src_root.rglob("*"):
            if not src_file.is_file():
                continue
            if src_file.name == ".gitkeep":
                # .gitkeep just ensures the parent dir exists in the copy —
                # honoring service relocation like any other scaffold path.
                rel = src_file.relative_to(src_root)
                if relocated_root and declared_root and str(rel).startswith(declared_root + "/"):
                    rel = Path(relocated_root) / str(rel)[len(declared_root) + 1 :]
                dest = project / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                continue

            rel = src_file.relative_to(src_root)
            if relocated_root and declared_root and str(rel).startswith(declared_root + "/"):
                rel = Path(relocated_root) / str(rel)[len(declared_root) + 1 :]
            if rel.parent.name == ".coding-os" and rel.name in COMPOSED_FILENAMES:
                # These are deep-merged from base + every stack by
                # compose_coding_os_configs — overlaying base first would
                # shadow the merge (first-writer-wins). See config-composition.md.
                continue
            dest = project / rel
            if dest.exists():
                # Idempotent: never overwrite existing project files.
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                content = src_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, ValueError):
                # Binary asset (image, font, ...) — copy verbatim, never substitute.
                shutil.copy2(src_file, dest)
                copied += 1
                continue
            content = _resolve_placeholders(content, substitutions)
            if src_file.suffix == ".md":
                skip_file, content = _apply_doc_conditions(content, disabled_modules, active_stacks)
                if skip_file:
                    continue
            dest.write_text(content, encoding="utf-8")
            shutil.copymode(src_file, dest)
            copied += 1

    return copied


def _copy_workflow_docs(project: Path) -> None:
    """Copy thinking_os-final-edition.md from src/core/docs/ into project workflow/.

    The full thinking_os reference is too large (57KB, 1439 lines) to duplicate
    in the scaffold dir. Instead, we copy it from src/core/docs/ at init time.
    """
    src = CORE_DIR / "docs" / "thinking_os-final-edition.md"
    if not src.exists():
        return
    dest = project / "docs" / "workflow" / "thinking_os-final-edition.md"
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
