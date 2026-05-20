"""cli.registry — global coding-os project registry + `cos registry` CLI."""

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
    """Resolve the global registry file path."""
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
    def from_dict(cls, data: dict[str, Any]) -> Registry:
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
    """Load the registry, returning an empty one if the file is absent."""
    path = registry_path()
    if not path.exists():
        return Registry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Registry file {path} is corrupt: {exc}. Inspect manually; do not auto-repair."
        )
    return Registry.from_dict(raw)


def save_registry(registry: Registry) -> None:
    """Atomically persist the registry."""
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
    """Register a project (idempotent on path; appends/updates slug)."""
    project_path = project_path.resolve()
    registry = load_registry()
    for existing in registry.projects:
        if Path(existing.path) == project_path:
            return existing
    final_slug = slug or _derive_slug(project_path)
    for existing in registry.projects:
        if existing.slug == final_slug:
            raise click.ClickException(
                f"Slug {final_slug!r} already used by {existing.path}. Pass --slug to pick another."
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
    pass


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


def _looks_like_cos_project(path: Path) -> bool:
    """Directory exists AND has a .coding-os/ subdirectory."""
    try:
        return path.is_dir() and (path / ".coding-os").is_dir()
    except OSError:
        return False


@registry_cli.command("gc")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Report what would be removed without mutating the registry.",
)
def registry_gc(dry_run: bool) -> None:
    """Prune registry entries whose directory no longer exists."""
    registry = load_registry()
    kept: list[ProjectEntry] = []
    removed: list[ProjectEntry] = []
    for entry in registry.projects:
        if _looks_like_cos_project(Path(entry.path)):
            kept.append(entry)
        else:
            removed.append(entry)

    if not removed:
        click.echo("registry is clean; nothing to remove.")
        return

    click.echo(
        f"{'Would remove' if dry_run else 'Removing'} "
        f"{len(removed)} stale entr{'y' if len(removed) == 1 else 'ies'}:"
    )
    for entry in removed:
        click.echo(f"  - {entry.slug:<24}  {entry.path}")

    if dry_run:
        click.echo("(dry-run — no changes written)")
        return
    registry.projects = kept
    save_registry(registry)
    click.echo(f"kept {len(kept)} entr{'y' if len(kept) == 1 else 'ies'}.")


@registry_cli.command("scan")
@click.argument("root", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--max-depth", default=6, show_default=True, type=int)
@click.option(
    "--limit", default=50, show_default=True, type=int, help="Cap the number of hits returned."
)
@click.option(
    "--register",
    is_flag=True,
    default=False,
    help="Register every hit that isn't already in the registry.",
)
def registry_scan(root: str, max_depth: int, limit: int, register: bool) -> None:
    """Walk ROOT and report every `.coding-os/` project found."""
    from collections import deque

    root_path = Path(root)
    max_depth = max(1, min(10, int(max_depth)))
    limit = max(1, min(500, int(limit)))

    skip = {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".coding-os",
        "dist",
        "build",
        ".next",
        ".turbo",
        "Library",
        "Trash",
        ".Trash",
    }
    registered_paths = {str(Path(p.path).resolve()) for p in load_registry().projects}

    hits: list[tuple[Path, bool]] = []
    queue: deque[tuple[Path, int]] = deque([(root_path, 0)])
    while queue and len(hits) < limit:
        current, depth = queue.popleft()
        if not current.is_dir():
            continue
        if _looks_like_cos_project(current):
            resolved = current.resolve()
            hits.append((resolved, str(resolved) in registered_paths))
            continue
        if depth >= max_depth:
            continue
        try:
            children = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for child in children:
            if not child.is_dir() or child.name in skip or child.name.startswith("."):
                continue
            queue.append((child, depth + 1))

    if not hits:
        click.echo(f"(no coding-os projects found under {root_path})")
        return

    click.echo(f"Found {len(hits)} project{'s' if len(hits) != 1 else ''} under {root_path}:")
    added = 0
    for path, already in hits:
        marker = "[registered]" if already else "[new]       "
        click.echo(f"  {marker}  {path}")
        if register and not already:
            try:
                add_project(path)
                added += 1
            except click.ClickException as exc:
                click.echo(f"    skip: {exc.message}", err=True)
    if register:
        click.echo(f"registered {added} new entr{'y' if added == 1 else 'ies'}.")
