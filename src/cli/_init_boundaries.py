"""Merge per-stack `scaffold-boundary.yaml` files into the consumer project.

Its own module because boundary aggregation changes for a different reason than
template overlay does: it tracks the boundary schema, not the file layout.
"""

from __future__ import annotations

from pathlib import Path

import click

from cli._init_registries import TEMPLATES_DIR, _get_stack_registry
from cli.stack_registry import service_relocations


def _aggregate_scaffold_boundaries(
    project: Path,
    state: Path,
    templates: list[str],
) -> None:
    """Merge per-stack `scaffold-boundary.yaml` files into the consumer."""
    import yaml

    stacks_data: list[dict] = []
    for stack_id in templates:
        boundary_src = TEMPLATES_DIR / stack_id / "scaffold-boundary.yaml"
        if not boundary_src.exists():
            continue
        try:
            data = yaml.safe_load(boundary_src.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise click.ClickException(
                f"src/templates/{stack_id}/scaffold-boundary.yaml is not valid YAML: {exc}"
            ) from exc
        if not isinstance(data, dict):
            continue
        stacks_data.append(
            {
                "stack": data.get("stack") or stack_id,
                "roots": list(data.get("roots") or []),
                "file_patterns": list(data.get("file_patterns") or []),
                "imports_from": list(data.get("imports_from") or []),
                "forbids_writing_in": list(data.get("forbids_writing_in") or []),
            }
        )

    target = state / "scaffold-boundary.yaml"
    if not stacks_data:
        if target.exists():
            target.unlink()
        return

    # Multi-backend relocation (project-anatomy.md): colliding declared roots
    # move each stack's boundary to src/services/<stack-id>/ BEFORE the
    # shared-root invariant — composed backends coexist by design.
    relocations = service_relocations(_get_stack_registry(), tuple(templates))
    if relocations:
        registry = _get_stack_registry()
        for entry in stacks_data:
            new_root = relocations.get(entry["stack"])
            if not new_root or entry["stack"] not in registry:
                continue
            declared = (registry[entry["stack"]].structure or {}).get("root", "").rstrip("/")
            if not declared:
                continue

            def _remap(path: str, declared: str = declared, new_root: str = new_root) -> str:
                stripped = path.rstrip("/")
                if stripped == declared or stripped.startswith(declared + "/"):
                    remapped = new_root + stripped[len(declared) :]
                    return remapped + "/" if path.endswith("/") else remapped
                return path

            entry["roots"] = [_remap(r) for r in entry["roots"]]
            entry["file_patterns"] = [_remap(p) for p in entry["file_patterns"]]

        # Cross-service walls: each relocated root becomes forbidden to every
        # OTHER stack, so an unowned write into a sibling service is flagged
        # (project-anatomy.md § Glob/verify propagation — parameterized, never
        # hand-listed in any stack's scaffold-boundary.yaml).
        for entry in stacks_data:
            for other_id, other_root in relocations.items():
                wall = other_root.rstrip("/") + "/"
                if other_id != entry["stack"] and wall not in entry["forbids_writing_in"]:
                    entry["forbids_writing_in"].append(wall)

    # Invariant 1: no two installed stacks may share a root.
    seen: dict[str, str] = {}
    for entry in stacks_data:
        for root in entry["roots"]:
            existing = seen.get(root)
            if existing and existing != entry["stack"]:
                raise click.ClickException(
                    f"scaffold-boundary aggregation: root '{root}' claimed by "
                    f"both '{existing}' and '{entry['stack']}'. Two installed "
                    f"stacks may not share a root — pick one per project."
                )
            seen[root] = entry["stack"]

    # Invariant 2: every forbid references an installed root OR `shared/`.
    all_roots = {root.rstrip("/") for root in seen}
    all_roots.add("shared")
    for entry in stacks_data:
        for forbidden in entry["forbids_writing_in"]:
            stripped = forbidden.rstrip("/")
            if stripped not in all_roots:
                # Soft: mention but do not fail — a stack may legitimately
                # forbid a subtree no installed stack owns yet.
                click.echo(
                    f"  WARN: stack '{entry['stack']}' forbids writes in "
                    f"'{forbidden}', but no installed stack owns that root.",
                    err=True,
                )

    aggregated = {
        "version": 1,
        "generated_by": "src/cli/_aggregate_scaffold_boundaries",
        "stacks": stacks_data,
    }
    target.write_text(
        yaml.safe_dump(aggregated, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    click.echo(
        f"  Aggregated scaffold-boundary for {len(stacks_data)} stack(s) → {target.relative_to(project)}"
    )
