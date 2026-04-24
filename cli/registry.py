"""cli.registry — global coding-os project registry + `cos registry` CLI.

PURPOSE: Maintain the list of coding-os projects installed on this
         machine, so the global Hub (port 9188) can enumerate them and
         route requests to each project's local sqlite DB.
INPUT:   JSON file at ~/.coding-os/registry.json (atomic writes).
OUTPUT:  Typed Registry + click subcommand group `cos registry`.
DEPENDENCIES: click, stdlib only (json, os, pathlib).
NOTES:   Schema v1.  Versioned envelope so future upgrades can migrate.
         Writes via tempfile + os.replace for crash-safe atomicity.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

REGISTRY_VERSION = 1


def registry_path() -> Path:
    """Resolve the global registry file path.

    PURPOSE: Single source-of-truth path for the cross-project registry.
    INPUT:   Optional env override COS_REGISTRY_PATH.
    OUTPUT:  Absolute Path; parent directory is created on demand by
             save_registry when needed (read-side stays pure).
    """
    override = os.environ.get("COS_REGISTRY_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".coding-os" / "registry.json"


@dataclass(frozen=True)
class ProjectEntry:
    """One registered coding-os project.

    slug: URL-safe short name (dirname by default; user-overridable).
    path: absolute project root — the directory with .coding-os/.
    created_at: ISO8601 UTC timestamp of first registration.
    """

    slug: str
    path: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )


@dataclass
class Registry:
    version: int = REGISTRY_VERSION
    projects: list[ProjectEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "projects": [asdict(p) for p in self.projects],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Registry":
        version = int(data.get("version", REGISTRY_VERSION))
        projects = [
            ProjectEntry(
                slug=str(p["slug"]),
                path=str(p["path"]),
                created_at=str(p.get("created_at", "")),
            )
            for p in data.get("projects", [])
        ]
        return cls(version=version, projects=projects)


def load_registry() -> Registry:
    """Load the registry, returning an empty one if the file is absent.

    PURPOSE: Safe read that never fails on missing file.
    OUTPUT:  Registry instance (may be empty).
    NOTES:   Malformed JSON raises click.ClickException so callers can
             abort cleanly; this is by design — silent repair would mask
             corruption.
    """
    path = registry_path()
    if not path.exists():
        return Registry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Registry file {path} is corrupt: {exc}. "
            "Inspect manually; do not auto-repair."
        )
    return Registry.from_dict(raw)


def save_registry(registry: Registry) -> None:
    """Atomically persist the registry.

    PURPOSE: Crash-safe write via tempfile + os.replace so a SIGKILL
             mid-write cannot leave a half-written JSON file.
    """
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(registry.to_dict(), indent=2, ensure_ascii=False) + "\n"
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=".registry-",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(payload)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, path)


def _derive_slug(project_path: Path) -> str:
    """Derive a URL-safe slug from a project directory name."""
    raw = project_path.name.lower().strip()
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in raw)
    cleaned = cleaned.strip("-") or "project"
    return cleaned


def add_project(project_path: Path, *, slug: str | None = None) -> ProjectEntry:
    """Register a project (idempotent on path; appends/updates slug).

    PURPOSE: Single write-side entry point used by `cos init` and the
             `cos registry add` CLI.
    INPUT:   project_path — absolute dir containing .coding-os/.
    OUTPUT:  The ProjectEntry that ended up in the registry.
    NOTES:   If path already registered, returns the existing entry
             (slug not overwritten to preserve user edits).  If slug
             collides with another path, raises ClickException.
    """
    project_path = project_path.resolve()
    registry = load_registry()
    for existing in registry.projects:
        if Path(existing.path) == project_path:
            return existing
    final_slug = slug or _derive_slug(project_path)
    for existing in registry.projects:
        if existing.slug == final_slug:
            raise click.ClickException(
                f"Slug {final_slug!r} already used by {existing.path}. "
                "Pass --slug to pick another."
            )
    entry = ProjectEntry(slug=final_slug, path=str(project_path))
    registry.projects.append(entry)
    save_registry(registry)
    return entry


def remove_project(selector: str) -> ProjectEntry | None:
    """Remove by slug or absolute path.  Returns removed entry or None."""
    registry = load_registry()
    target = None
    for p in registry.projects:
        if p.slug == selector or p.path == selector:
            target = p
            break
    if target is None:
        return None
    registry.projects = [p for p in registry.projects if p is not target]
    save_registry(registry)
    return target


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group(name="registry", help="Manage the global coding-os project registry.")
def registry_cli() -> None:
    """PURPOSE: Parent group so `cos registry …` shows consistent help."""


@registry_cli.command("list")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def registry_list(fmt: str) -> None:
    """List all registered coding-os projects."""
    registry = load_registry()
    if fmt == "json":
        click.echo(json.dumps(registry.to_dict(), indent=2))
        return
    if not registry.projects:
        click.echo("(no projects registered yet — run `cos init` in a project)")
        return
    click.echo(f"coding-os projects ({len(registry.projects)}):")
    for p in registry.projects:
        click.echo(f"  {p.slug:<24}  {p.path}")


@registry_cli.command("add")
@click.argument("project_dir", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--slug", default=None, help="Override the derived slug.")
def registry_add(project_dir: str, slug: str | None) -> None:
    """Add an existing coding-os project to the registry."""
    path = Path(project_dir)
    if not (path / ".coding-os").is_dir():
        raise click.ClickException(
            f"{path} has no .coding-os/ directory — run `cos init` there first."
        )
    entry = add_project(path, slug=slug)
    click.echo(f"Registered {entry.slug} → {entry.path}")


@registry_cli.command("remove")
@click.argument("selector")
def registry_remove(selector: str) -> None:
    """Remove a project by slug or absolute path."""
    removed = remove_project(selector)
    if removed is None:
        raise click.ClickException(f"No project found for {selector!r}")
    click.echo(f"Removed {removed.slug} ({removed.path})")


@registry_cli.command("path")
@click.argument("slug")
def registry_get_path(slug: str) -> None:
    """Print the absolute path for a given slug (for shell scripts)."""
    for p in load_registry().projects:
        if p.slug == slug:
            click.echo(p.path)
            return
    click.echo(f"No project with slug {slug!r}", err=True)
    sys.exit(1)
