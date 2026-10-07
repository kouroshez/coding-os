"""graph_os — map a Go import path to the in-repo package directory it names.

The importer's nearest `go.mod` gives a module path and root; a root `go.work`
adds every module it `use`s, and a `replace X => ../dir` in that go.mod maps X
to a folder of the repo. An import path at or under one of those module paths
names a directory in the repo — anything else is a third-party package.
"""

from __future__ import annotations

import logging
import posixpath
import re
from pathlib import Path, PurePosixPath

logger = logging.getLogger("graph_os.resolve_go")

_MODULE_RE = re.compile(r"^module\s+\"?([^\"\s]+)\"?\s*$", re.MULTILINE)
_USE_BLOCK_RE = re.compile(r"^use\s*\(([^)]*)\)", re.MULTILINE)
_USE_LINE_RE = re.compile(r"^use\s+([^\s(]+)\s*$", re.MULTILINE)
_MAJOR_VERSION_RE = re.compile(r"^v\d+$")
_GOPKG_VERSION_RE = re.compile(r"\.v\d+$")

# `replace example.com/lib [v1.2.3] => ../lib`, alone or inside a `replace ( … )` block.
_LOCAL_REPLACE_RE = re.compile(
    r"^\s*(?:replace\s+)?(\S+)(?:\s+\S+)?\s*=>\s*(\.\.?/\S*)\s*$", re.MULTILINE
)

_MODULE_CACHE: dict[tuple[str, int], str] = {}


def package_dir(importer: str, import_path: str, root: Path) -> str | None:
    """Repo-relative directory of the in-repo package `import_path`, or None."""
    for module_path, module_dir in _modules_for(importer, root):
        if import_path == module_path:
            rest = ""
        elif import_path.startswith(f"{module_path}/"):
            rest = import_path[len(module_path) + 1 :]
        else:
            continue
        candidate = "/".join(part for part in (module_dir, rest) if part) or "."
        if (root / candidate).is_dir():
            return candidate
    return None


def default_package_name(import_path: str) -> str:
    """The name a Go file uses for an import that has no alias."""
    segments = [segment for segment in import_path.split("/") if segment]
    if len(segments) > 1 and _MAJOR_VERSION_RE.match(segments[-1]):
        segments.pop()
    name = _GOPKG_VERSION_RE.sub("", segments[-1]) if segments else import_path
    name = name.removeprefix("go-").removesuffix("-go")
    return name.replace("-", "_").replace(".", "_")


def _modules_for(importer: str, root: Path) -> list[tuple[str, str]]:
    modules: dict[str, str] = {}
    nearest = _nearest_go_mod(root, str(PurePosixPath(importer).parent))
    if nearest is not None:
        modules[nearest[0]] = nearest[1]
        for module_path, target in _local_replaces(root, nearest[1]):
            modules.setdefault(module_path, target)
    for module_dir in _workspace_dirs(root):
        module_path = _module_path(root / module_dir / "go.mod")
        if module_path:
            modules.setdefault(module_path, module_dir)
    return sorted(modules.items(), key=lambda item: -len(item[0]))


def _nearest_go_mod(root: Path, directory: str) -> tuple[str, str] | None:
    current: str | None = directory
    while current is not None:
        module_dir = "" if current in ("", ".") else current
        module_path = _module_path(root / module_dir / "go.mod")
        if module_path:
            return module_path, module_dir
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return None


def _local_replaces(root: Path, module_dir: str) -> list[tuple[str, str]]:
    try:
        text = (root / module_dir / "go.mod").read_text(encoding="utf-8")
    except OSError:
        return []
    replaces = []
    for module_path, target in _LOCAL_REPLACE_RE.findall(text):
        joined = posixpath.normpath(posixpath.join(module_dir or ".", target))
        if not joined.startswith(".."):
            replaces.append((module_path, "" if joined == "." else joined))
    return replaces


def _workspace_dirs(root: Path) -> list[str]:
    go_work = root / "go.work"
    if not go_work.is_file():
        return []
    try:
        text = go_work.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("go.work unreadable: %s", exc)
        return []
    entries = [line for block in _USE_BLOCK_RE.findall(text) for line in block.split()]
    entries.extend(_USE_LINE_RE.findall(text))
    return [PurePosixPath(entry).as_posix().removeprefix("./") for entry in entries]


def _module_path(go_mod: Path) -> str:
    try:
        mtime = go_mod.stat().st_mtime_ns
    except OSError:
        return ""
    key = (str(go_mod), mtime)
    if key not in _MODULE_CACHE:
        try:
            match = _MODULE_RE.search(go_mod.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.debug("go.mod unreadable %s: %s", go_mod, exc)
            match = None
        _MODULE_CACHE[key] = match.group(1) if match else ""
    return _MODULE_CACHE[key]


__all__ = ["default_package_name", "package_dir"]
