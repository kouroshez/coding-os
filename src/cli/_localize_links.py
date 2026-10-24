"""Keep every link `cos` writes inside the repository, so a clone is agent-ready.

Spec: docs/architecture/adr/0010-consumer-distribution-version-gate.md § Amendment.

The installers still write absolute symlinks into the coding-os install; this
module converts them afterwards and back again before the next install step, so
every other command keeps working on plain symlinks:

- in coding-os itself, a link becomes relative (the target is in the same repo);
- in a consumer, a hook becomes a relative link to the tracked hook shim, and any
  other asset (rule, skill, command) becomes a real copy.

`.coding-os/managed-files.json` (tracked) records each converted path's source
and the hash cos wrote, so `delocalize` restores only untouched copies and a
file the user edited stays theirs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from cli._cli_paths import CODING_OS_ROOT
from cli._init_registries import CONFIG_FILE, STATE_DIR, _get_adapter_registry
from cli._resources import core_dir, data_root

SHIM_NAME = "hook-shim.sh"
MANAGED_FILES = "managed-files.json"
# .provenance.json names this machine's import paths; the agent never reads it.
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".provenance.json")
# Sourced, never run: shimming one would `exec` inside the hook that sources it.
# Hooks find these beside their real file once the shim runs them from there.
_SOURCED_LIBRARY = "cos-env.sh"


def _is_executable_hook(name: str) -> bool:
    return name.endswith(".sh") and not name.startswith("_") and name != _SOURCED_LIBRARY


@dataclass
class LocalizeReport:
    relinked: int = 0
    copied: int = 0
    shimmed: int = 0
    kept_edits: list[str] = field(default_factory=list)


def _is_meta(project: Path) -> bool:
    return project.resolve() == CODING_OS_ROOT.resolve()


def _asset_dirs(project: Path, agents: Iterable[str]) -> list[tuple[Path, bool]]:
    registry = _get_adapter_registry()
    dirs: list[tuple[Path, bool]] = []
    for agent in agents:
        profile = registry.get(agent)
        if profile is None:
            continue
        for rel, is_hooks in (
            (profile.hooks_dir, True),
            (profile.rules_dir, False),
            (profile.skills_dir, False),
            (profile.commands_dir, False),
        ):
            if rel and (project / rel).is_dir():
                dirs.append((project / rel, is_hooks))
    return dirs


def _roots() -> dict[str, Path]:
    # Where install links point: the coding-os install, and the community skill
    # library in ~/.coding-os/skills — both are outside any clone.
    from cli._skill_project import user_skills_dir

    return {"core": data_root().resolve(), "library": user_skills_dir().resolve()}


def _links(base: Path) -> list[Path]:
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(base):
        found.extend(
            p for p in (Path(current) / n for n in (*dirnames, *filenames)) if p.is_symlink()
        )
    return found


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for item in files:
        sha.update(item.relative_to(path).as_posix().encode() if path.is_dir() else b"")
        sha.update(item.read_bytes())
    return sha.hexdigest()


def _manifest_path(project: Path) -> Path:
    return project / STATE_DIR / MANAGED_FILES


def _load_manifest(project: Path) -> dict[str, dict]:
    try:
        return json.loads(_manifest_path(project).read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError, KeyError):
        return {}


def _save_manifest(project: Path, entries: dict[str, dict]) -> None:
    body = {"version": 1, "entries": dict(sorted(entries.items()))}
    _manifest_path(project).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def managed_copies(project: Path) -> set[str]:
    """Project-relative paths cos copied verbatim from core (never rendered)."""
    return {rel for rel, entry in _load_manifest(project).items() if entry["kind"] == "copy"}


def managed_names(project: Path, base_rel: str) -> set[str]:
    """Names directly under an adapter dir that cos wrote (incl. ones the user now owns)."""
    prefix = base_rel.rstrip("/") + "/"
    return {
        rel[len(prefix) :].split("/")[0]
        for rel in _load_manifest(project)
        if rel.startswith(prefix)
    }


def _relink(link: Path, target: Path) -> None:
    link.unlink()
    link.symlink_to(os.path.relpath(target, link.parent))


def localize(project: Path, agents: Iterable[str]) -> LocalizeReport:
    """Convert the install's absolute links under the agents' adapter dirs."""
    project = project.resolve()
    report = LocalizeReport()
    meta = _is_meta(project)
    entries = {} if meta else _load_manifest(project)
    shim = project / STATE_DIR / SHIM_NAME
    if not meta:
        shim.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(core_dir("scripts", SHIM_NAME), shim)
        shim.chmod(0o755)
    roots = _roots()
    for base, is_hooks in _asset_dirs(project, agents):
        for link in _links(base):
            target = link.resolve()
            if not target.exists():
                continue
            if project in target.parents:
                # The project's own content (a skill imported from skills/<name>).
                if os.path.isabs(os.readlink(link)):
                    _relink(link, target)
                    report.relinked += 1
                continue
            key = next((k for k, r in roots.items() if r in target.parents), None)
            if key is None or (meta and key != "core"):
                continue
            rel = link.relative_to(project).as_posix()
            source = target.relative_to(roots[key]).as_posix()
            if meta:
                _relink(link, target)
                report.relinked += 1
            elif is_hooks and link.parent == base and _is_executable_hook(link.name):
                _relink(link, shim)
                entries[rel] = {"root": key, "source": source, "kind": "shim"}
                report.shimmed += 1
            elif is_hooks and link.parent == base:
                # A library or helper the hook finds beside its real file; the
                # shim runs the real file, so the link would only dangle.
                link.unlink()
                entries[rel] = {"root": key, "source": source, "kind": "dropped"}
            else:
                link.unlink()
                if target.is_dir():
                    shutil.copytree(target, link, ignore=_COPY_IGNORE)
                else:
                    shutil.copy2(target, link)
                entries[rel] = {
                    "root": key,
                    "source": source,
                    "kind": "copy",
                    "sha256": _digest(link),
                }
                report.copied += 1
    if not meta:
        _save_manifest(project, entries)
    return report


def delocalize(project: Path) -> list[str]:
    """Turn untouched managed copies and shim links back into install links."""
    project = project.resolve()
    if _is_meta(project):
        return []
    entries = _load_manifest(project)
    roots = _roots()
    kept: list[str] = []
    for rel, entry in list(entries.items()):
        path = project / rel
        source = roots[entry.get("root", "core")] / entry["source"]
        if entry["kind"] == "dropped":
            if not (path.exists() or path.is_symlink()) and source.exists():
                path.symlink_to(source)
            del entries[rel]
            continue
        if not (path.exists() or path.is_symlink()):
            del entries[rel]
            continue
        edited = entry["kind"] == "copy" and _digest(path) != entry.get("sha256")
        if entry["kind"] == "owned" or edited:
            entries[rel] = {**entry, "kind": "owned"}
            kept.append(rel)
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        if source.exists():
            path.symlink_to(source)
        del entries[rel]
    _save_manifest(project, entries)
    return kept


def _configured_agents(project: Path) -> list[str]:
    import yaml

    try:
        data = yaml.safe_load((project / CONFIG_FILE).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return list(data.get("agents") or [])


@contextmanager
def link_form(project: Path, agents: Iterable[str] | None = None) -> Iterator[list[str]]:
    """Run an install step on plain links, then localize what it wrote.

    A copy the user edited is moved aside for the step — `ln -sf` would replace
    it — and put back before localizing, so it stays theirs. `agents` defaults
    to the project's `.coding-os.yaml::agents`.
    """
    import tempfile

    project = project.resolve()
    agents = list(agents) if agents is not None else _configured_agents(project)
    kept = delocalize(project)
    with tempfile.TemporaryDirectory(prefix="cos-kept-") as parking:
        for rel in kept:
            (Path(parking) / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(project / rel), str(Path(parking) / rel))
        try:
            yield kept
        finally:
            for rel in kept:
                path = project / rel
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                elif path.exists() or path.is_symlink():
                    path.unlink()
                shutil.move(str(Path(parking) / rel), str(path))
            localize(project, agents)
