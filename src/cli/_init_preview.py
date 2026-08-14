"""`cos init --dry-run` previews — what WOULD be written, never a mutation.

Separate from the scaffold engine because it changes for presentation reasons,
not materialisation ones; keeping it here stops a print tweak from touching the
code that actually writes a consumer's tree.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from cli._init_registries import CONFIG_FILE, STATE_DIR, TEMPLATES_DIR, _get_stack_registry
from cli._init_scaffold import _apply_doc_conditions, _service_relocations
from cli.config_composer import COMPOSED_FILENAMES


def _dry_config_preview(templates: tuple[str, ...], output_format: str) -> None:
    """`cos init --dry-config` — merged .coding-os preview, zero writes."""
    from cli.config_composer import preview_coding_os_configs

    merged, conflicts = preview_coding_os_configs(list(templates), templates_dir=TEMPLATES_DIR)
    if output_format == "json":
        click.echo(
            json.dumps(
                {"stacks": list(templates), "configs": merged, "conflicts": conflicts},
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    scrumban = merged.get("scrumban-config.yaml") or {}
    lanes = [lane.get("id") for lane in scrumban.get("swimlanes") or [] if isinstance(lane, dict)]
    click.echo(f"Merge preview for stacks: {', '.join(templates) or '(base only)'}")
    click.echo(f"  swimlanes: {', '.join(lanes) or '(none)'}")
    for filename in merged:
        click.echo(f"  composed: {filename}")
    if conflicts:
        click.echo(f"  conflicts ({len(conflicts)} — later wins):")
        for line in conflicts:
            click.echo(f"    WARN: {line}")
    else:
        click.echo("  conflicts: none")
    click.echo("(dry-config — nothing written)")


def _scaffold_tree_preview(
    templates: tuple[str, ...], disabled_modules: tuple[str, ...] = ()
) -> tuple[list[str], list[str]]:
    """Relative paths `cos init` WOULD create — zero reads of the target, zero writes.

    Returns (sorted paths, config-merge conflicts). Mirrors the source roots,
    service-relocation logic AND the `<!-- module:X -->` doc-skip of
    `_overlay_scaffold` / `_run_scaffold_phase` so the preview matches what an
    actual init writes (audit INIT-4). disabled_modules is taken LITERALLY from the
    validated `--disable-module` flags; the real init additionally resolves
    dependency-refusal (e.g. `docs` stays enabled while `tasks` depends on it) and
    preset-declared disables at scaffold time, so for those two cases the preview
    is a best-effort upper bound on what gets dropped, not byte-exact (pass-3).
    """
    from cli.config_composer import preview_coding_os_configs

    relocations = _service_relocations(templates)
    registry = _get_stack_registry()
    disabled_set = {m.strip() for m in disabled_modules if m.strip()}
    active_set = set(templates)
    paths: set[str] = set()

    sources: list[tuple[Path, str | None]] = [(TEMPLATES_DIR / "_base" / "scaffold", None)]
    for name in templates:
        # Community stacks resolve from source_dir, not the bundled tree.
        stack_root = registry[name].source_dir if name in registry else TEMPLATES_DIR / name
        candidate = stack_root / "scaffold"
        if candidate.exists():
            sources.append((candidate, name))

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
            if not src_file.is_file() or src_file.name == ".gitkeep":
                continue
            rel = src_file.relative_to(src_root)
            # A module-tagged doc the actual --disable-module init would drop
            # must not appear in the preview (INIT-4: preview == actual). Only
            # .md files carry the marker, mirroring the overlay's own scope.
            if disabled_set and src_file.suffix == ".md":
                try:
                    skip_file, _ = _apply_doc_conditions(
                        src_file.read_text(encoding="utf-8"), disabled_set, active_set
                    )
                    if skip_file:
                        continue
                except OSError as exc:
                    logging.getLogger(__name__).debug(
                        "doc-condition preview check skipped for %s: %s", src_file, exc
                    )
            if relocated_root and declared_root and str(rel).startswith(declared_root + "/"):
                rel = Path(relocated_root) / str(rel)[len(declared_root) + 1 :]
            # Composed configs come from the merge step below, not the overlay.
            if rel.parent.name == ".coding-os" and rel.name in COMPOSED_FILENAMES:
                continue
            paths.add(str(rel))

    merged, conflicts = preview_coding_os_configs(list(templates), templates_dir=TEMPLATES_DIR)
    for filename in merged:
        paths.add(f"{STATE_DIR}/{filename}")

    # Generated artifacts the scaffold phase always writes (not under scaffold/).
    paths.update(
        {
            CONFIG_FILE,
            "AGENTS.md",
            "Makefile",
            f"{STATE_DIR}/coding-os.db",
            f"{STATE_DIR}/Makefile.base",
        }
    )
    return sorted(paths), conflicts


def _dry_run_preview(
    templates: tuple[str, ...], output_format: str, disabled_modules: tuple[str, ...] = ()
) -> None:
    """`cos init --dry-run` — preview the scaffold tree with ZERO writes."""
    paths, conflicts = _scaffold_tree_preview(templates, disabled_modules)
    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "stacks": list(templates),
                    "disabled_modules": [m for m in disabled_modules if m],
                    "files": paths,
                    "conflicts": conflicts,
                    "note": "the .claude/ agent surface (hooks/skills/commands/rules) is installed by the adapter and NOT previewed here",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    click.echo(f"Scaffold preview for stacks: {', '.join(templates) or '(base only)'}")
    click.echo(f"  {len(paths)} file(s) would be created:")
    for path in paths:
        click.echo(f"    {path}")
    if conflicts:
        click.echo(f"  config conflicts ({len(conflicts)} — later wins):")
        for line in conflicts:
            click.echo(f"    WARN: {line}")
    click.echo(
        "  note: the .claude/ agent surface (hooks · skills · commands · rules) is "
        "installed by the adapter and NOT previewed here."
    )
    click.echo("(dry-run — nothing written)")
