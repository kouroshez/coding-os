"""cli.sync_all — push the meta-repo's current state to every registered project.

PURPOSE: Close the "I edited core/ or adapters/, how do consumer projects
         pick it up?" gap.  Symlinks already propagate core/hooks / core/rules
         live, but three paths need explicit re-runs:
           1. adapters/<agent>/*.template.* → .claude/settings.json (RENDER,
              not symlink) — must be re-rendered per install.sh.
           2. .coding-os/thinking_os.db pending migrations (e.g. v19 "drop
              ready status") — applied lazily via init_db.
           3. Broken symlinks if the meta repo itself moved — symlink
              targets become dangling; this surfaces + repairs them.

INPUT:   ~/.coding-os/registry.json, every project's .coding-os.yaml.
OUTPUT:  Click command group `cos sync-all` + `cos sync-doctor`.
DEPENDENCIES: cli.registry (project list), cli.main (_run_adapter_install /
              _link_stack_skills), core.thinking_os.db (init_db).
NOTES:   All mutations are idempotent — re-running is safe.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CORE_DIR = _REPO_ROOT / "core"
ADAPTERS_DIR = _REPO_ROOT / "adapters"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_project_config(project: Path) -> dict:
    cfg = project / ".coding-os.yaml"
    if not cfg.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — best-effort scan
        click.echo(f"    WARN: could not parse {cfg}: {exc}", err=True)
        return {}


def _iter_symlinks(project: Path) -> list[Path]:
    """Yield every symlink under a consumer project's agent dirs.

    PURPOSE: Symlinks to core/hooks, core/rules, core/skills are the
             propagation mechanism — a dangling one means install.sh
             wrote it against an old meta repo location that no longer
             exists.  We surface them for --repair.
    """
    out: list[Path] = []
    for agent_dir in (".claude", ".codex", ".cursor"):
        root = project / agent_dir
        if not root.exists():
            continue
        for sub in ("hooks", "rules", "skills", "commands"):
            d = root / sub
            if not d.exists():
                continue
            try:
                for entry in d.rglob("*"):
                    if entry.is_symlink():
                        out.append(entry)
            except (OSError, PermissionError):
                continue
    return out


def _dangling(link: Path) -> bool:
    """True when a symlink's target path no longer exists."""
    try:
        return not link.resolve(strict=True).exists()
    except (FileNotFoundError, RuntimeError):
        return True
    except OSError:
        return True


def _apply_migrations(project: Path) -> tuple[bool, str]:
    """Run init_db on the project's thinking_os.db.  Returns (ok, msg)."""
    db_path = project / ".coding-os" / "thinking_os.db"
    if not db_path.exists():
        return True, "no DB (pre-Phase-C install)"
    try:
        from core.thinking_os.db import get_schema_version, init_db  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return False, f"import failed: {exc}"
    try:
        conn = init_db(db_path)
        try:
            ver = get_schema_version(conn)
        finally:
            conn.close()
        return True, f"schema v{ver}"
    except Exception as exc:  # noqa: BLE001
        return False, f"migration error: {exc}"


def _re_run_installs(project: Path, agents: list[str],
                     templates: tuple[str, ...], dry_run: bool) -> list[str]:
    """Re-run each declared adapter's install.sh — idempotent re-link."""
    notes: list[str] = []
    if dry_run:
        for ag in agents:
            notes.append(f"would re-run adapters/{ag}/install.sh")
        return notes
    from cli.main import _link_stack_skills, _run_adapter_install  # type: ignore
    for ag in agents:
        try:
            _run_adapter_install(ag, project)
            if templates:
                _link_stack_skills(ag, templates, project)
            notes.append(f"re-linked {ag}")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"FAILED {ag}: {exc}")
    return notes


def _each_registered_project(only_slug: str | None = None):
    """Yield (entry, path) for every registered project whose dir exists."""
    from cli.registry import load_registry  # type: ignore
    reg = load_registry()
    for entry in reg.projects:
        if only_slug and entry.slug != only_slug:
            continue
        path = Path(entry.path)
        if not (path / ".coding-os").is_dir():
            click.echo(f"  SKIP {entry.slug}: {path} (no .coding-os/)", err=True)
            continue
        yield entry, path


# ---------------------------------------------------------------------------
# cos sync-all
# ---------------------------------------------------------------------------


@click.command("sync-all", help="Propagate meta-repo state to every registered project.")
@click.option("--slug", default=None,
              help="Sync only the project with this slug (default: all).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Report what would be done without mutating anything.")
@click.option("--skip-installs", is_flag=True, default=False,
              help="Skip adapter install.sh re-run (migrations + symlink check only).")
def sync_all_cmd(slug: str | None, dry_run: bool, skip_installs: bool) -> None:
    """Re-render adapter templates, re-link symlinks, apply DB migrations.

    For each registered project:
      1. Re-run declared adapter install.sh scripts (idempotent).
      2. Trigger init_db on .coding-os/thinking_os.db (applies any
         pending schema migrations such as v19 "drop ready status").
      3. Audit agent-dir symlinks; report dangling ones.
    """
    total = 0
    seen_broken: dict[str, list[str]] = {}
    click.echo(f"coding-os sync-all  [meta repo: {_REPO_ROOT}]")
    if dry_run:
        click.echo("  (dry-run — no mutation)")

    for entry, path in _each_registered_project(slug):
        total += 1
        click.echo(f"\n• {entry.slug}  ({path})")

        cfg = _load_project_config(path)
        agents = list(cfg.get("agents") or [])
        templates = tuple(cfg.get("templates") or [])

        if not agents:
            click.echo("    (no agents configured in .coding-os.yaml — skipping installs)")
        elif not skip_installs:
            for note in _re_run_installs(path, agents, templates, dry_run):
                click.echo(f"    {note}")

        ok, msg = (True, "skipped (dry-run)") if dry_run else _apply_migrations(path)
        marker = "✓" if ok else "✗"
        click.echo(f"    {marker} migrations: {msg}")

        links = _iter_symlinks(path)
        dangling = [str(link) for link in links if _dangling(link)]
        if dangling:
            seen_broken[entry.slug] = dangling
            click.echo(f"    ⚠ {len(dangling)} dangling symlink(s) "
                       f"(run `cos sync-doctor --slug {entry.slug} --repair`)")
        else:
            click.echo(f"    ✓ {len(links)} symlink(s) healthy")

    click.echo(f"\n{total} project(s) processed.")
    if seen_broken:
        click.echo(f"{sum(len(v) for v in seen_broken.values())} dangling link(s) across "
                   f"{len(seen_broken)} project(s).  Use `cos sync-doctor --repair`.")


# ---------------------------------------------------------------------------
# cos sync-doctor
# ---------------------------------------------------------------------------


@click.command("sync-doctor", help="Audit and optionally repair per-project symlinks.")
@click.option("--slug", default=None, help="Check only this project.")
@click.option("--repair", is_flag=True, default=False,
              help="Re-run install.sh on projects with dangling links to fix them.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def sync_doctor_cmd(slug: str | None, repair: bool, fmt: str) -> None:
    """Walk each project's agent dirs, flag broken symlinks.

    PURPOSE: When the meta repo moves (e.g. user relocates ~/coding-os)
             every install.sh-written symlink becomes dangling — hooks
             silently stop firing.  This surfaces + repairs them.
    OUTPUT:  Text or JSON.  Exit code = number of projects still broken
             AFTER the optional --repair pass (so CI can gate on it).
    """
    report: list[dict] = []
    for entry, path in _each_registered_project(slug):
        links = _iter_symlinks(path)
        dangling = [str(link) for link in links if _dangling(link)]
        repaired = False
        if dangling and repair:
            cfg = _load_project_config(path)
            agents = list(cfg.get("agents") or [])
            templates = tuple(cfg.get("templates") or [])
            if agents:
                for note in _re_run_installs(path, agents, templates, dry_run=False):
                    if fmt == "text":
                        click.echo(f"    {note}")
                # Re-scan.
                links = _iter_symlinks(path)
                dangling = [str(link) for link in links if _dangling(link)]
                repaired = True
        report.append({
            "slug": entry.slug,
            "path": str(path),
            "total_links": len(links),
            "dangling": dangling,
            "repaired_attempted": repaired,
        })

    if fmt == "json":
        click.echo(json.dumps(report, indent=2))
    else:
        for r in report:
            if not r["dangling"]:
                click.echo(f"✓ {r['slug']}: {r['total_links']} links healthy")
                continue
            suffix = " (after repair)" if r["repaired_attempted"] else ""
            click.echo(f"✗ {r['slug']}: {len(r['dangling'])} dangling{suffix}")
            for link in r["dangling"]:
                click.echo(f"    {link}")

    still_broken = sum(1 for r in report if r["dangling"])
    sys.exit(min(still_broken, 125))  # click convention — cap at 125
