"""Task linting and board configuration: task-validate and board-config."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from cli._board_cli_shared import (
    _REPO_ROOT,
    _db_conn,
    _project_root,
)

# ---------------------------------------------------------------------------
# task-validate / board-config
# ---------------------------------------------------------------------------


@click.command(
    "task-validate",
    help=(
        "Lint task files, OR pre-flight a transition without applying it.\n\n"
        "  cos task-validate                       lint all docs/tasks/*.md (default)\n"
        "  cos task-validate TASK-NN               preview DoR for in_progress on TASK-NN\n"
        "  cos task-validate TASK-NN --for complete  preview DoD for complete\n"
        "  cos task-validate TASK-NN --json        machine-readable ValidationResult"
    ),
)
@click.argument("task_id", required=False)
@click.option(
    "--for",
    "for_status",
    type=click.Choice(["in_progress", "complete"]),
    default="in_progress",
    help="Status to validate as the target. Default: in_progress (DoR check).",
)
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option(
    "--repair",
    is_flag=True,
    default=False,
    help="Lint mode only: drop stale duplicate frontmatter blocks in place, then re-sync.",
)
def task_validate_cmd(task_id, for_status, as_json, repair):
    """Two modes:

    1. No TASK_ID → lint every TASK-*.md file (legacy behavior).
    2. TASK_ID given → run the transition gate for the given
       target status WITHOUT applying it. Same validator as the live
       gate, so the verdict matches what `cos task-start` would do.
    """
    if not task_id:
        _task_validate_lint_all(repair=repair)
        return
    if repair:
        click.echo("ERROR: --repair applies to lint mode only (drop the TASK_ID).", err=True)
        sys.exit(2)
    _task_validate_preflight(task_id, for_status, as_json)


def _task_validate_lint_all(*, repair: bool = False) -> None:
    from board_os.parser import (
        detect_duplicate_frontmatter,
        parse_task,
        repair_duplicate_frontmatter,
    )

    root = _project_root()
    tasks_dir = root / "docs" / "tasks"
    if not tasks_dir.exists():
        click.echo(f"  (no {tasks_dir})")
        return
    errors = 0
    warnings = 0
    repaired = 0
    for p in sorted(tasks_dir.glob("TASK-*.md")):
        content = p.read_text(encoding="utf-8")
        duplicate = detect_duplicate_frontmatter(content)
        if duplicate and repair:
            fixed = repair_duplicate_frontmatter(content)
            if fixed is not None:
                p.write_text(fixed, encoding="utf-8")
                click.echo(f"  ⟳ {p.name}: repaired (stale duplicate block dropped)")
                repaired += 1
                content, duplicate = fixed, None
        if duplicate:
            click.echo(f"  ✗ {p.name}: {duplicate}", err=True)
            errors += 1
            continue
        parsed = parse_task(content, path=p)
        if parsed is None:
            click.echo(f"  ✗ {p.name}: unparseable", err=True)
            errors += 1
            continue
        if parsed.parse_warnings:
            for w in parsed.parse_warnings:
                click.echo(f"  ⚠ {p.name}: {w}")
                warnings += 1
        else:
            click.echo(f"  ✓ {p.name}")
    if repaired:
        # A repaired file was previously rejected by sync_one, so its DB row is
        # stale — re-sync before reporting success or the board keeps the old
        # priority/status it was frozen at.
        _resync_repaired_tasks(root)
    suffix = f", {repaired} repaired" if repaired else ""
    click.echo(f"\n  Total: {errors} errors, {warnings} warnings{suffix}")
    sys.exit(1 if errors > 0 else 0)


def _resync_repaired_tasks(root: Path) -> None:
    from board_os.sync import sync_all

    conn = _db_conn()
    try:
        stats = sync_all(conn, root)
    except Exception as exc:
        click.echo(f"  ⚠ re-sync failed ({exc}) — run `cos task-sync` manually", err=True)
        return
    finally:
        conn.close()
    click.echo(f"  ⟳ board re-synced: {stats['upserted']} upserted of {stats['scanned']} scanned")


def _task_validate_preflight(task_id: str, for_status: str, as_json: bool) -> None:
    """Run the transition gate validator without applying any change."""

    from board_os.parser import extract_frontmatter
    from board_os.transition_gates import GatesConfigError, load_gates_config
    from board_os.transition_gates_cli import (
        _has_work_log_entries,
        _verify_state,
    )
    from board_os.transition_gates_validator import (
        Verdict,
        validate_transition,
    )

    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT file_path, kind FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        click.echo(f"ERROR: {task_id} not found", err=True)
        sys.exit(1)

    file_path = _project_root() / row[0] if row[0] else None
    body = ""
    kind = str(row[1] or "feature")
    if file_path and file_path.exists():
        body = file_path.read_text(encoding="utf-8")
        fm = extract_frontmatter(body) or {}
        if fm.get("kind"):
            kind = str(fm["kind"])

    try:
        config = load_gates_config()
    except GatesConfigError as exc:
        click.echo(f"ERROR: gates config: {exc}", err=True)
        sys.exit(2)

    has_recent, age = _verify_state()
    has_work_log = _has_work_log_entries(body)

    result = validate_transition(
        task_id=task_id,
        kind=kind,
        body=body,
        new_status=for_status,
        config=config,
        has_recent_verify=has_recent,
        verify_age_seconds=age,
        has_work_log=has_work_log,
        override_reason=os.environ.get("COS_OVERRIDE_REASON"),
        override_actor=os.environ.get("COS_AGENT"),
    )

    if as_json:
        click.echo(result.model_dump_json(indent=2))
        sys.exit(0 if result.verdict is not Verdict.BLOCK else 2)

    glyph = {
        Verdict.PASS: "✓ PASS",
        Verdict.WARN: "⚠ WARN",
        Verdict.BLOCK: "✗ BLOCK",
    }[result.verdict]
    click.echo(f"  {task_id} (kind={kind}, target={for_status}): {glyph}")
    for msg in result.messages:
        sev = msg.severity.value.upper()
        click.echo(f"    [{msg.code}] {sev}: {msg.message}")
    if result.verdict is Verdict.PASS:
        click.echo(
            f"  Run: cos task-start {task_id}"
            if for_status == "in_progress"
            else f"  Run: cos task-done {task_id}"
        )
    sys.exit(0 if result.verdict is not Verdict.BLOCK else 2)


def _discover_stacks() -> list[str]:
    """Data-driven — read templates/ to find available stack ids."""
    templates_dir = _REPO_ROOT / "src" / "templates"
    if not templates_dir.exists():
        return []
    return sorted(
        p.name for p in templates_dir.iterdir() if p.is_dir() and (p / "scaffold").exists()
    )


@click.command("board-config", help="Scaffold or inspect scrumban-config.yaml")
@click.option("--init", is_flag=True, default=False)
@click.option("--stack", default="_base")
def board_config_cmd(init, stack):
    valid_stacks = _discover_stacks() or ["_base"]
    if stack not in valid_stacks:
        click.echo(
            f"ERROR: stack {stack!r} not in {valid_stacks}",
            err=True,
        )
        sys.exit(1)
    root = _project_root()
    config_path = root / ".coding-os" / "scrumban-config.yaml"
    if init:
        if config_path.exists():
            click.echo(f"ERROR: {config_path} already exists", err=True)
            sys.exit(1)
        source = (
            _REPO_ROOT
            / "src"
            / "templates"
            / stack
            / "scaffold"
            / ".coding-os"
            / "scrumban-config.yaml"
        )
        if not source.exists():
            source = (
                _REPO_ROOT
                / "src"
                / "templates"
                / "_base"
                / "scaffold"
                / ".coding-os"
                / "scrumban-config.yaml"
            )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo(f"  Created {config_path} (from {stack})")
    else:
        if not config_path.exists():
            click.echo(f"ERROR: {config_path} not found; run --init", err=True)
            sys.exit(1)
        click.echo(config_path.read_text(encoding="utf-8"))
