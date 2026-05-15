"""`cos list-adapters` — show the adapter registry.

Mirror of `list-stacks` for the agent adapter layer. Discovers every
`src/adapters/<id>/adapter.yaml` file and prints a summary table or JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli.adapter_registry import load_adapter_registry

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
ADAPTERS_DIR = CODING_OS_ROOT / "src" / "adapters"


def _yn(flag: bool) -> str:
    return "yes" if flag else "no"


def _render_text(adapters: dict) -> str:
    if not adapters:
        return "(no adapters found)"
    col1 = max(len(a.id) for a in adapters.values())
    col2 = max(len(a.label) for a in adapters.values())
    col3 = max(len(a.settings_file or "—") for a in adapters.values())
    header = (
        f"{'ID':<{col1}}  "
        f"{'LABEL':<{col2}}  "
        f"{'SETTINGS FILE':<{col3}}  "
        f"RULES  SETTINGS"
    )
    divider = "-" * len(header)
    lines = [header, divider]
    for a in sorted(adapters.values(), key=lambda a: a.id):
        lines.append(
            f"{a.id:<{col1}}  "
            f"{a.label:<{col2}}  "
            f"{(a.settings_file or '—'):<{col3}}  "
            f"{_yn(a.supports_rules):<5}  "
            f"{_yn(a.supports_settings_json)}"
        )
    return "\n".join(lines)


def _render_json(adapters: dict) -> str:
    payload = {
        "adapters": [
            {
                "id": a.id,
                "label": a.label,
                "settings_file": a.settings_file,
                "hooks_dir": a.hooks_dir,
                "rules_dir": a.rules_dir,
                "skills_dir": a.skills_dir,
                "supports_rules": a.supports_rules,
                "supports_settings_json": a.supports_settings_json,
                "sourced_hooks": list(a.sourced_hooks),
            }
            for a in sorted(adapters.values(), key=lambda a: a.id)
        ],
    }
    return json.dumps(payload, indent=2)


@click.command("list-adapters")
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def list_adapters(output_format: str) -> None:
    """List all available adapters discovered from adapters/*/adapter.yaml."""
    adapters = load_adapter_registry(ADAPTERS_DIR)
    if output_format == "json":
        click.echo(_render_json(adapters))
    else:
        click.echo(_render_text(adapters))
