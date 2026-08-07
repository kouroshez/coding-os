from __future__ import annotations

import json
from pathlib import Path

import click

from thinking_os.supervision import policy_snapshot, update_policy


def _project_root(raw: str) -> Path:
    root = Path(raw).resolve()
    if not (root / ".coding-os").is_dir():
        raise click.ClickException(
            f"{root} is not a coding-os project (.coding-os/ missing) — run from the project root."
        )
    return root


def _emit_snapshot(root: Path, output_format: str) -> None:
    snapshot = policy_snapshot(root)
    if output_format == "json":
        click.echo(json.dumps(snapshot, indent=2))
        return
    policy = snapshot["policy"]
    click.echo(f"Supervision: {'enabled' if policy['enabled'] else 'disabled'}")
    click.echo(
        f"Mode: {policy['mode']} · threshold: {policy['complexity_threshold']} · "
        f"fallback: {policy['fallback_policy']} · parallel: {policy['max_parallel']}"
    )
    cooldown = policy["cooldown"]
    click.echo(
        f"Cooldown: {cooldown['default_seconds']}s default · {cooldown['maximum_seconds']}s maximum"
    )
    orchestrator = policy["orchestrator"]
    click.echo(
        "Orchestrator: "
        + "/".join(
            (
                orchestrator["adapter"] or "current-adapter",
                orchestrator["model"] or "default-model",
                orchestrator["effort"] or "default-effort",
            )
        )
    )
    roles = policy["roles"]
    click.echo("Roles: " + (", ".join(sorted(roles)) if roles else "none"))
    adapters = snapshot["adapters"]
    click.echo("Eligible adapters: " + (", ".join(row["id"] for row in adapters) or "none"))
    click.echo(f"Settings: {snapshot['settings_path']}")


def _update(root: Path, patch: dict, **kwargs) -> None:
    try:
        update_policy(root, patch, **kwargs)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@click.group("supervision")
def supervision_group() -> None:
    """Inspect and configure agent supervision without Hub."""


@supervision_group.command("show")
@click.option("-d", "--project-dir", default=".", show_default=True, type=click.Path())
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def supervision_show(project_dir: str, output_format: str) -> None:
    """Show the normalized project policy and eligible adapters."""
    _emit_snapshot(_project_root(project_dir), output_format)


def _toggle(project_dir: str, enabled: bool, output_format: str) -> None:
    root = _project_root(project_dir)
    _update(root, {"enabled": enabled})
    _emit_snapshot(root, output_format)


@supervision_group.command("enable")
@click.option("-d", "--project-dir", default=".", show_default=True, type=click.Path())
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def supervision_enable(project_dir: str, output_format: str) -> None:
    """Enable supervision for this project."""
    _toggle(project_dir, True, output_format)


@supervision_group.command("disable")
@click.option("-d", "--project-dir", default=".", show_default=True, type=click.Path())
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def supervision_disable(project_dir: str, output_format: str) -> None:
    """Disable supervision while preserving its policy."""
    _toggle(project_dir, False, output_format)


@supervision_group.command("set")
@click.option("-d", "--project-dir", default=".", show_default=True, type=click.Path())
@click.option("--mode", type=click.Choice(["explicit", "suggest", "adaptive"]))
@click.option(
    "--complexity-threshold",
    type=click.Choice(["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC"]),
)
@click.option(
    "--fallback-policy",
    type=click.Choice(["fail_closed", "same_adapter_default", "next_eligible"]),
)
@click.option("--max-parallel", type=click.IntRange(1, 16))
@click.option("--cooldown-default-seconds", type=click.IntRange(1, 86400))
@click.option("--cooldown-maximum-seconds", type=click.IntRange(1, 604800))
@click.option("--orchestrator-adapter")
@click.option("--orchestrator-model")
@click.option("--orchestrator-effort")
@click.option("--clear-orchestrator", is_flag=True)
@click.option("--role")
@click.option("--role-adapter")
@click.option("--role-model")
@click.option("--role-effort")
@click.option("--clear-role", is_flag=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def supervision_set(
    project_dir: str,
    mode: str | None,
    complexity_threshold: str | None,
    fallback_policy: str | None,
    max_parallel: int | None,
    cooldown_default_seconds: int | None,
    cooldown_maximum_seconds: int | None,
    orchestrator_adapter: str | None,
    orchestrator_model: str | None,
    orchestrator_effort: str | None,
    clear_orchestrator: bool,
    role: str | None,
    role_adapter: str | None,
    role_model: str | None,
    role_effort: str | None,
    clear_role: bool,
    output_format: str,
) -> None:
    """Partially update routing, cooldown, orchestrator, or one role policy."""
    root = _project_root(project_dir)
    patch: dict = {}
    for key, value in (
        ("mode", mode),
        ("complexity_threshold", complexity_threshold),
        ("fallback_policy", fallback_policy),
        ("max_parallel", max_parallel),
    ):
        if value is not None:
            patch[key] = value
    cooldown = {
        key: value
        for key, value in (
            ("default_seconds", cooldown_default_seconds),
            ("maximum_seconds", cooldown_maximum_seconds),
        )
        if value is not None
    }
    if cooldown:
        patch["cooldown"] = cooldown
    orchestrator = {
        key: value
        for key, value in (
            ("adapter", orchestrator_adapter),
            ("model", orchestrator_model),
            ("effort", orchestrator_effort),
        )
        if value is not None
    }
    if orchestrator:
        patch["orchestrator"] = orchestrator
    role_values = {
        key: value
        for key, value in (
            ("adapter", role_adapter),
            ("model", role_model),
            ("effort", role_effort),
        )
        if value is not None
    }
    if (role_values or clear_role) and not role:
        raise click.UsageError("--role is required with role options or --clear-role")
    if clear_role and role_values:
        raise click.UsageError("--clear-role cannot be combined with --role-adapter/model/effort")
    if orchestrator and clear_orchestrator:
        raise click.UsageError(
            "--clear-orchestrator cannot be combined with --orchestrator-adapter/model/effort"
        )
    if role_values and role:
        patch["roles"] = {role: role_values}
    if not patch and not clear_role and not clear_orchestrator:
        raise click.UsageError("provide at least one setting to update")
    _update(
        root,
        patch,
        clear_role=(role or "") if clear_role else "",
        clear_orchestrator=clear_orchestrator,
    )
    _emit_snapshot(root, output_format)
