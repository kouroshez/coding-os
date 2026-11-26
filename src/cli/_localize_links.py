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

import os
import re
import shutil
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from cli._cli_paths import CODING_OS_ROOT
from cli._init_registries import CONFIG_FILE, STATE_DIR, _get_adapter_registry
from cli._init_scaffold import TOOL_OUTPUT
from cli._managed_manifest import (
    PROVENANCE_FILE,
    SHARED_SKILLS_DIR,
    _digest,
    _save_manifest,
    load_manifest,
)
from cli._resources import core_dir, data_root

SHIM_NAME = "hook-shim.sh"
# The cross-agent skills root (Codex reads it natively); other agents link into it.
# .provenance.json names this machine's import paths; the agent never reads it.
_COPY_IGNORE = shutil.ignore_patterns(*TOOL_OUTPUT, "*.pyc", PROVENANCE_FILE)
# Sourced, never run: shimming one would `exec` inside the hook that sources it.
# Hooks find these beside their real file once the shim runs them from there.
_SOURCED_LIBRARY = "cos-env.sh"
# One pass, left to right: a fence or HTML comment, then a link (whose text
# may hold code spans), then an inline code span. Splitting on code first cut a link like
# [`path`](target) in two, so a dangling one survived localization.
_SEGMENT = re.compile(
    r"(?P<fence>```.*?```|~~~.*?~~~|<!--.*?-->)"
    r"|(?P<link>\[(?P<text>(?:[^\]\n`]|`[^`\n]*`)+)\]\((?P<target>[^)\s]+)\))"
    r"|(?P<code>``[^\n]*?``|`[^`\n]*`)",
    re.S,
)


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
            (profile.agents_dir, False),
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


def _load_manifest(project: Path) -> dict[str, dict]:
    return load_manifest(project, _roots())


def managed_copies(project: Path) -> set[str]:
    """Project-relative paths cos copied verbatim from core (never rendered)."""
    return {rel for rel, entry in _load_manifest(project).items() if entry["kind"] == "copy"}


def managed_names(project: Path, base_rel: str, *, skip_source: str = "") -> set[str]:
    """Names directly under an adapter dir that cos wrote (incl. ones the user now owns)."""
    prefix = base_rel.rstrip("/") + "/"
    return {
        rel[len(prefix) :].split("/")[0]
        for rel, entry in _load_manifest(project).items()
        if rel.startswith(prefix)
        and not (skip_source and entry.get("source", "").startswith(skip_source))
    }


def user_owns(project: Path, rel: str) -> bool:
    path = project / rel
    resolved = path.resolve()
    if resolved != path.absolute() and project.resolve() in resolved.parents:
        path = resolved  # read through an alias to the shared copy it points at
        rel = resolved.relative_to(project.resolve()).as_posix()
    if _roots()["core"] in resolved.parents:
        return False  # read through a folder link into the coding-os install
    if path.is_symlink() or not path.exists():
        return False
    entry = _load_manifest(project).get(rel)
    if entry is None or entry["kind"] == "owned":
        return True
    return entry["kind"] == "copy" and _digest(path) != entry.get("sha256")


def _untouched_copies(project: Path, skill_rel: str, files: dict[str, dict]) -> bool:
    return all(_digest(project / skill_rel / sub) == e.get("sha256") for sub, e in files.items())


def _alias_shared_skills(project: Path, entries: dict[str, dict]) -> None:
    if not (project / SHARED_SKILLS_DIR).is_dir():
        return
    skills: dict[str, dict[str, dict]] = {}
    for rel, entry in entries.items():
        parts = rel.split("/")
        if entry["kind"] == "copy" and len(parts) == 4 and parts[1] == "skills":
            skills.setdefault("/".join(parts[:3]), {})[parts[3]] = entry
    for skill_rel, files in skills.items():
        shared_rel = f"{SHARED_SKILLS_DIR}/{skill_rel.rsplit('/', 1)[1]}"
        shared = skills.get(shared_rel)
        skill_path = project / skill_rel
        if (
            skill_rel == shared_rel
            or shared is None
            or {sub: (e["root"], e["source"]) for sub, e in files.items()}
            != {sub: (e["root"], e["source"]) for sub, e in shared.items()}
            or {p.name for p in skill_path.iterdir()} != set(files)
            or not _untouched_copies(project, skill_rel, files)
            or not _untouched_copies(project, shared_rel, shared)
        ):
            continue
        shutil.rmtree(skill_path)
        skill_path.symlink_to(os.path.relpath(project / shared_rel, skill_path.parent))
        for sub in files:
            del entries[f"{skill_rel}/{sub}"]
        sources = {sub: {"root": e["root"], "source": e["source"]} for sub, e in files.items()}
        entries[skill_rel] = {"kind": "alias", "target": shared_rel, "files": sources}


def _unalias_shared_skills(project: Path, entries: dict[str, dict]) -> None:
    roots = _roots()
    for rel, entry in list(entries.items()):
        if entry["kind"] != "alias":
            continue
        path = project / rel
        if not path.is_symlink():
            del entries[rel]
            continue  # the user replaced the link with a skill of their own
        target = entry["target"]
        shared = {sub: entries.get(f"{target}/{sub}") for sub in entry["files"]}
        if any(
            e is None or e["kind"] != "copy" or _digest(project / target / sub) != e.get("sha256")
            for sub, e in shared.items()
        ):
            continue  # edited through the alias: both agents keep reading the edit
        del entries[rel]
        path.unlink()
        path.mkdir()
        for sub, origin in entry["files"].items():
            source = roots[origin["root"]] / origin["source"]
            if source.exists():
                (path / sub).symlink_to(source)


def _unlink_missing(copy: Path, project: Path) -> None:
    # A copied page keeps links written for the coding-os tree. One whose target
    # this project lacks would send the agent to a file that is not there, so it
    # becomes its plain text. Code spans and fences are examples, left as written.
    if copy.is_dir():
        # _templates hold placeholder links on purpose; doc-lint skips them too.
        pages = sorted(p for p in copy.rglob("*.md") if "_templates" not in p.parts)
    else:
        pages = [copy] if copy.suffix == ".md" else []
    for page in pages:
        base = page.parent

        def _text_if_missing(match: re.Match[str], base: Path = base) -> str:
            image = match.start() > 0 and match.string[match.start() - 1] == "!"
            if match.group("link") is None or image:
                return match.group(0)  # a fence, comment, code span or image: kept as written
            target = unquote(match.group("target").split("#", 1)[0])
            if not target or "://" in target or target.startswith(("/", "mailto:")):
                return match.group(0)
            # A library page is third-party text: a target outside the project
            # is never probed, and a path the OS refuses counts as missing.
            # Containment is lexical: a sibling still linked into the install
            # (localized later in this pass) is inside the project all the same.
            try:
                resolved = Path(os.path.normpath(base / target))
                kept = project in resolved.parents and resolved.exists()
            except (OSError, ValueError):
                kept = False
            return match.group(0) if kept else match.group("text")

        try:
            original = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rewritten = _SEGMENT.sub(_text_if_missing, original)
        if rewritten != original:
            page.write_text(rewritten, encoding="utf-8")


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
                _unlink_missing(link, project)
                # A whole skill folder is recorded per child, the shape aliasing
                # and delocalize read.
                skill_folder = key == "core" and (target / "SKILL.md").is_file()
                parts = sorted(link.iterdir()) if skill_folder else [link]
                for part in parts:
                    entries[part.relative_to(project).as_posix()] = {
                        "root": key,
                        "source": source if part == link else f"{source}/{part.name}",
                        "kind": "copy",
                        "sha256": _digest(part),
                    }
                report.copied += 1
    if not meta:
        _alias_shared_skills(project, entries)
        _save_manifest(project, entries)
    return report


def delocalize(project: Path) -> list[str]:
    """Turn untouched managed copies and shim links back into install links."""
    project = project.resolve()
    if _is_meta(project):
        return []
    entries = _load_manifest(project)
    _unalias_shared_skills(project, entries)
    roots = _roots()
    kept: list[str] = []
    for rel, entry in list(entries.items()):
        if entry["kind"] == "alias":
            continue  # kept by _unalias_shared_skills: the shared copy holds an edit
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


def _unfold_outside_links(project: Path, path: Path) -> None:
    # The step may have folded the edit's skill dir into a folder link into the
    # install; restoring through it would write the edit into the shared source.
    # Such a link becomes a real dir of links to its children again first.
    current = project
    for part in path.relative_to(project).parts[:-1]:
        current = current / part
        if not current.is_symlink() or project in current.resolve().parents:
            continue
        target = current.resolve()
        if not target.is_dir():
            continue
        current.unlink()
        current.mkdir()
        for child in target.iterdir():
            (current / child.name).symlink_to(child)


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
    parking = Path(tempfile.mkdtemp(prefix="cos-kept-"))
    for rel in kept:
        (parking / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(project / rel), str(parking / rel))
    try:
        yield kept
    finally:
        failed: list[OSError] = []
        for rel in kept:
            path = project / rel
            try:
                _unfold_outside_links(project, path)
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                elif path.exists() or path.is_symlink():
                    path.unlink()
                # The step may have removed the dir the edit lived in.
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(parking / rel), str(path))
            except OSError as exc:
                failed.append(exc)
        localize(project, agents)
        if failed:
            # An edit that did not go back stays here, never in a deleted temp dir.
            raise OSError(f"{failed[0]} — your unrestored edits are kept in {parking}")
        shutil.rmtree(parking, ignore_errors=True)
