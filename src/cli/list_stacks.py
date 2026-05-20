"""`cos list-stacks` — show the stack registry.

Pure read-only command. Does not touch the filesystem outside loading
templates/*/stack.yaml. Use to discover what stacks can be passed to
`cos init --stack <id>` or `cos add-stack <id>`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from cli.stack_registry import load_stack_registry

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = CODING_OS_ROOT / "src" / "templates"


def _render_text(registry, warnings: tuple[str, ...]) -> str:
    if not registry.stacks:
        body = "(no stacks found)"
    else:
        col1 = max(len(s.id) for s in registry.values())
        col2 = max(len(s.category) for s in registry.values())
        col3 = max(len(s.primary_skill or "—") for s in registry.values())
        header = f"{'ID':<{col1}}  {'CATEGORY':<{col2}}  {'PRIMARY SKILL':<{col3}}  LABEL"
        divider = "-" * len(header)
        lines = [header, divider]
        for stack in sorted(registry.values(), key=lambda s: s.id):
            lines.append(
                f"{stack.id:<{col1}}  "
                f"{stack.category:<{col2}}  "
                f"{(stack.primary_skill or '—'):<{col3}}  "
                f"{stack.label}"
            )
        body = "\n".join(lines)

    warn_block = ""
    if warnings:
        warn_block = "\n\nWarnings:\n" + "\n".join(f"  • {w}" for w in warnings)

    return body + warn_block


def _render_json(registry, warnings: tuple[str, ...]) -> str:
    payload = {
        "stacks": [
            {
                "id": s.id,
                "label": s.label,
                "category": s.category,
                "primary_skill": s.primary_skill,
                "skills": list(s.skills),
            }
            for s in sorted(registry.values(), key=lambda s: s.id)
        ],
        "warnings": list(warnings),
    }
    return json.dumps(payload, indent=2)


@click.command("list-stacks")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def list_stacks(output_format: str) -> None:
    """List all available stacks discovered from templates/*/stack.yaml."""
    registry = load_stack_registry(TEMPLATES_DIR)
    if output_format == "json":
        click.echo(_render_json(registry, registry.warnings))
    else:
        click.echo(_render_text(registry, registry.warnings))
    # Non-zero exit only when there are hard load errors (warnings present
    # AND zero stacks loaded) so scripts can detect a fully-broken registry.
    if not registry.stacks and registry.warnings:
        sys.exit(1)
