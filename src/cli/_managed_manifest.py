"""managed-files.json: every file cos copied, shimmed or aliased into a project.

The manifest is committed, so it is untrusted input: an entry is used only after
its paths pass the checks here. Spec: docs/architecture/adr/0010-consumer-distribution-version-gate.md § Amendment.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from cli._init_registries import STATE_DIR, _get_adapter_registry

SHARED_SKILLS_DIR = ".agents/skills"
MANAGED_FILES = "managed-files.json"
PROVENANCE_FILE = ".provenance.json"


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for item in files:
        sha.update(item.relative_to(path).as_posix().encode() if path.is_dir() else b"")
        sha.update(item.read_bytes())
    return sha.hexdigest()


def _manifest_path(project: Path) -> Path:
    return project / STATE_DIR / MANAGED_FILES


def load_manifest(project: Path, roots: dict[str, Path]) -> dict[str, dict]:
    """Entries of the project's manifest that pass every path check."""
    try:
        entries = json.loads(_manifest_path(project).read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError, KeyError):
        return {}
    if not isinstance(entries, dict):
        return {}
    # The manifest is committed, so a clone or a PR can write it: every path it
    # names is checked before anything deletes, moves or links there.
    prefixes = _asset_prefixes()
    return {
        rel: entry
        for rel, entry in entries.items()
        if _safe_entry(project, rel, entry, roots, prefixes)
    }


_ENTRY_KINDS = frozenset({"shim", "dropped", "copy", "owned", "alias"})


def _plain_name(name: object) -> bool:
    return isinstance(name, str) and len(Path(name).parts) == 1 and _plain_relative(name)


def _plain_relative(path: str) -> bool:
    parts = Path(path).parts
    return (
        bool(parts)
        and not os.path.isabs(path)
        and ".." not in parts
        and PROVENANCE_FILE not in parts
    )


def _asset_prefixes() -> tuple[str, ...]:
    dirs = {SHARED_SKILLS_DIR}
    for adapter_id, profile in _get_adapter_registry().items():
        # Where older installs put an agent's skills and commands: still cos's to migrate.
        dirs.update({f".{adapter_id}/skills", f".{adapter_id}/commands"})
        for rel in (
            profile.hooks_dir,
            profile.rules_dir,
            profile.skills_dir,
            profile.commands_dir,
            profile.agents_dir,
        ):
            if rel:
                dirs.add(rel.rstrip("/"))
    return tuple(f"{d}/" for d in dirs)


def _safe_entry(
    project: Path, rel: object, entry: object, roots: dict[str, Path], prefixes: tuple[str, ...]
) -> bool:
    if not isinstance(rel, str) or not isinstance(entry, dict):
        return False
    if entry.get("kind") not in _ENTRY_KINDS or not _plain_relative(rel):
        return False
    if not rel.startswith(prefixes):
        return False
    home = project.resolve()
    parent = (project / rel).parent.resolve()
    if parent != home and home not in parent.parents:
        return False
    files = entry.get("files")
    if entry["kind"] == "alias":
        if not isinstance(files, dict) or not all(_plain_name(name) for name in files):
            return False
        target = entry.get("target")
        if not isinstance(target, str) or not _plain_relative(target):
            return False
        if not target.startswith(f"{SHARED_SKILLS_DIR}/"):
            return False
        origins = list(files.values())
    else:
        origins = [entry]
    for origin in origins:
        if not isinstance(origin, dict) or origin.get("root", "core") not in roots:
            return False
        source = origin.get("source")
        if not isinstance(source, str) or not _plain_relative(source):
            return False
    return True


def _save_manifest(project: Path, entries: dict[str, dict]) -> None:
    body = {"version": 1, "entries": dict(sorted(entries.items()))}
    _manifest_path(project).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
