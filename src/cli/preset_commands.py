"""`cos preset list|create|export|import` — custom preset authoring (TASK-365).

User presets live in ~/.coding-os/presets ($COS_USER_PRESETS_DIR override) and
join discovery everywhere load_preset_registry runs (init --preset, wizard,
list-stacks, hub). Schema: src/core/schemas/preset.schema.json.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import click
import yaml

from cli._resources import templates_dir
from cli.preset_registry import load_preset_registry, user_presets_dir
from cli.stack_registry import load_stack_registry


def _known_stacks() -> set[str]:
    return set(load_stack_registry(templates_dir()).keys())


def _registry():
    return load_preset_registry(templates_dir(), known_stacks=_known_stacks())


@click.group("preset")
def preset_group() -> None:
    """Author, share and inspect project presets (named stack compositions)."""


@preset_group.command("list")
def preset_list() -> None:
    """Show every discoverable preset (shipped + user)."""
    registry = _registry()
    user_dir = user_presets_dir()
    for preset in sorted(registry.values(), key=lambda p: p.id):
        origin = "user" if preset.source_path.parent == user_dir else "shipped"
        click.echo(f"  {preset.id:<22} {origin:<8} {' + '.join(preset.stacks)}")
    for warning in registry.warnings:
        click.echo(f"  WARN: {warning}", err=True)


@preset_group.command("create")
@click.option("--id", "preset_id", required=True, help="Lowercase kebab-case identifier.")
@click.option("--label", required=True, help="Human-readable name shown in discovery.")
@click.option("--stacks", "stacks_csv", required=True, help="Comma-separated stack ids, in order.")
@click.option("--description", default="", help="What this composition is for.")
@click.option("--skills", "skills_csv", default="", help="Extra core skills, comma-separated.")
def preset_create(
    preset_id: str, label: str, stacks_csv: str, description: str, skills_csv: str
) -> None:
    """Save a custom composition as a schema-valid user preset."""
    stacks = [s.strip() for s in stacks_csv.split(",") if s.strip()]
    unknown = [s for s in stacks if s not in _known_stacks()]
    if unknown:
        raise click.ClickException(f"unknown stack(s) {unknown} — see `cos list-stacks`")
    if preset_id in _registry():
        raise click.ClickException(
            f"preset '{preset_id}' already exists — pick another id or remove the old file"
        )

    payload: dict = {"version": 1, "id": preset_id, "label": label, "stacks": stacks}
    if description:
        payload["description"] = description
    skills = [s.strip() for s in skills_csv.split(",") if s.strip()]
    if skills:
        payload["skills"] = skills

    target_dir = user_presets_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{preset_id}.yaml"
    target.write_text(yaml.dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # Round-trip through the real loader so a bad preset never lands silently.
    reloaded = _registry()
    if preset_id not in reloaded:
        target.unlink(missing_ok=True)
        raise click.ClickException(
            "preset failed validation after write — " + "; ".join(reloaded.warnings[-3:])
        )
    click.echo(f"created {target} — usable now: cos init --preset {preset_id}")


@preset_group.command("export")
@click.argument("preset_id")
@click.option("--out", "out_path", default=None, help="Destination file (default: ./<id>.yaml).")
def preset_export(preset_id: str, out_path: str | None) -> None:
    """Emit a shareable preset file (re-import with `cos preset import`)."""
    registry = _registry()
    if preset_id not in registry:
        raise click.ClickException(
            f"preset '{preset_id}' not found — available: {sorted(registry.keys())}"
        )
    destination = Path(out_path) if out_path else Path.cwd() / f"{preset_id}.yaml"
    shutil.copyfile(registry[preset_id].source_path, destination)
    click.echo(f"exported {preset_id} → {destination}")


@preset_group.command("import")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def preset_import(source: Path) -> None:
    """Validate a shared preset file and install it into the user preset dir."""
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise click.ClickException(f"{source} is not valid YAML: {exc}")
    if not isinstance(data, dict) or not data.get("id"):
        raise click.ClickException(f"{source} is not a preset file (missing id)")
    preset_id = str(data["id"])
    if preset_id in _registry():
        raise click.ClickException(f"preset '{preset_id}' already exists — not overwriting")

    target_dir = user_presets_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{preset_id}.yaml"
    shutil.copyfile(source, target)
    reloaded = _registry()
    if preset_id not in reloaded:
        target.unlink(missing_ok=True)
        raise click.ClickException(
            "preset failed validation — " + "; ".join(reloaded.warnings[-3:])
        )
    click.echo(f"imported {preset_id} — usable now: cos init --preset {preset_id}")
