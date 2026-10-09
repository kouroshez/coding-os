"""graph_os — resolve a TypeScript/JavaScript import specifier to the repo file it names.

Mirrors the parts of TypeScript's `bundler` resolution an index needs: relative
paths with extension and index probing (including the ESM `./x.js` → `x.ts` /
`x.d.ts` convention and React Native platform variants), the nearest
tsconfig/jsconfig `paths` and `baseUrl` — through `extends` (relative or a
workspace package's preset), `${configDir}`, and the `references` project whose
`include` holds the file — workspace packages through package.json `exports` /
`types` / `main`, and `#` subpath imports through the nearest package.json
`imports`. A condition naming a file the repo lacks (an unbuilt `dist`) falls
through to the next. A specifier that names no repo file resolves to None, and
the caller keeps its external-package uid.
"""

from __future__ import annotations

import fnmatch
import logging
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ._resolve_ts_files import (
    _join,
    _mtime,
    _probe,
    _read_json,
    platform_twins,
)

logger = logging.getLogger("graph_os.resolve_ts")

CONFIG_NAMES = ("tsconfig.json", "jsconfig.json")
EXTENDS_DEPTH_LIMIT = 8
EXPORT_CONDITIONS = ("types", "import", "module", "react-native", "browser", "default", "require")
CONFIG_DIR = "${configDir}"

_WORKSPACE_GLOB_RE = re.compile(r"^\s*-\s*['\"]?([^'\"#\s]+)['\"]?", re.MULTILINE)


@dataclass(frozen=True)
class _TsProject:
    aliases: tuple[tuple[str, tuple[str, ...]], ...]
    base_url: str | None


_PROJECT_CACHE: dict[tuple[str, int], _TsProject] = {}
_WORKSPACE_CACHE: dict[tuple[str, int], dict[str, str]] = {}
# A solution tsconfig's referenced configs, and each config's `files` / `include` as regexes.
_REFERENCES_CACHE: dict[tuple[str, int], tuple[str, ...]] = {}
_INCLUDE_CACHE: dict[tuple[str, int], tuple[tuple[bool, re.Pattern[str]], ...]] = {}


def resolve(importer: str, specifier: str, root: Path) -> str | None:
    """Repo-relative path of the file `specifier` names from `importer`, or None."""
    if specifier.startswith("."):
        base = _join(str(PurePosixPath(importer).parent), specifier)
        return _probe(root, base) if base is not None else None
    project = _nearest_project(root, importer)
    if specifier.startswith("#"):
        # tsconfig `paths` (`#/*`, Nuxt's `#app`) come before package.json `imports`.
        for target in _alias_targets(project, specifier, include_base_url=False):
            hit = _probe(root, target)
            if hit:
                return hit
        return _resolve_subpath_import(root, importer, specifier)
    for target in _alias_targets(project, specifier, include_base_url=True):
        hit = _probe(root, target)
        if hit:
            return hit
    return _resolve_workspace_package(root, specifier)


def alias_target(importer: str, specifier: str, root: Path) -> str | None:
    """First explicit `paths` substitution for `specifier`, whether or not the file exists."""
    project = _nearest_project(root, importer)
    return next(iter(_alias_targets(project, specifier, include_base_url=False)), None)


def _alias_targets(
    project: _TsProject | None, specifier: str, *, include_base_url: bool
) -> list[str]:
    if project is None:
        return []
    targets: list[str] = []
    for pattern, replacements in project.aliases:
        # A catch-all `*` also maps every third-party package, so only a file
        # that exists (the caller's probe) may claim it — never a guess.
        if pattern == "*" and not include_base_url:
            continue
        captured = _match_pattern(pattern, specifier)
        if captured is not None:
            targets.extend(target.replace("*", captured, 1) for target in replacements)
    if include_base_url and project.base_url is not None:
        joined = _join(project.base_url, specifier)
        if joined is not None:
            targets.append(joined)
    return targets


def _match_pattern(pattern: str, specifier: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == specifier else None
    prefix, _, suffix = pattern.partition("*")
    fits = specifier.startswith(prefix) and specifier.endswith(suffix)
    if not fits or len(specifier) < len(prefix) + len(suffix):
        return None
    return specifier[len(prefix) : len(specifier) - len(suffix)]


def _nearest_project(root: Path, importer: str) -> _TsProject | None:
    current: str | None = str(PurePosixPath(importer).parent)
    while current is not None:
        for name in CONFIG_NAMES:
            config = f"{current}/{name}" if current not in ("", ".") else name
            if (root / config).is_file():
                return _load_project(root, _owning_config(root, config, importer))
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return None


def _owning_config(root: Path, config: str, importer: str) -> str:
    # The config that holds the file keeps it; a solution config (`files: []`)
    # hands it to the referenced project whose include holds it.
    if _includes(root, config, importer):
        return config
    return next(
        (
            reference
            for reference in _references(root, config)
            if _includes(root, reference, importer)
        ),
        config,
    )


def _references(root: Path, config: str) -> tuple[str, ...]:
    key = (str(root / config), _mtime(root / config))
    if key not in _REFERENCES_CACHE:
        found: list[str] = []
        for entry in _read_json(root / config).get("references") or []:
            path = entry.get("path") if isinstance(entry, dict) else None
            target = (
                _join(str(PurePosixPath(config).parent), path) if isinstance(path, str) else None
            )
            if target is not None and (root / target).is_dir():
                target = f"{target}/tsconfig.json"
            if target is not None and (root / target).is_file():
                found.append(target)
        _REFERENCES_CACHE[key] = tuple(found)
    return _REFERENCES_CACHE[key]


def _includes(root: Path, config: str, importer: str) -> bool:
    # Entries are relative to the config's folder; only one that climbs out
    # (`../../packages/shared/src`) reaches a file outside it, as `**` never does.
    config_dir = str(PurePosixPath(config).parent)
    relative = importer if config_dir in ("", ".") else posixpath.relpath(importer, config_dir)
    key = (str(root / config), _mtime(root / config))
    if key not in _INCLUDE_CACHE:
        data = _read_json(root / config)
        files = [entry for entry in data.get("files") or [] if isinstance(entry, str)]
        patterns = data.get("include")
        if not isinstance(patterns, list):
            patterns = [] if "files" in data else ["**/*"]
        exact = [_against(config_dir, entry) for entry in files]
        globs = [_against(config_dir, entry) for entry in patterns if isinstance(entry, str)]
        _INCLUDE_CACHE[key] = tuple(
            [(_climbs(entry), re.compile(re.escape(entry) + "$")) for entry in exact]
            + [(_climbs(entry), _glob(entry)) for entry in globs]
        )
    outside = relative.startswith("../")
    return any(
        climbs == outside and pattern.match(relative) for climbs, pattern in _INCLUDE_CACHE[key]
    )


def _climbs(entry: str) -> bool:
    return PurePosixPath(entry).parts[:1] == ("..",)


def _against(config_dir: str, entry: str) -> str:
    # `../web/src` in apps/web is `src`; `src/../../shared` is `../shared`.
    base = config_dir if config_dir not in ("", ".") else "."
    return posixpath.relpath(posixpath.normpath(posixpath.join(base, entry)), base)


def _glob(pattern: str) -> re.Pattern[str]:
    # tsconfig include: `**/` spans folders, `*` and `?` stay in one segment, and a
    # last segment without a wildcard or extension names a folder.
    parts = [part for part in pattern.removeprefix("./").split("/") if part not in ("", ".")]
    last = parts[-1] if parts else "**"
    if last == "**":
        parts.append("*")
    elif "*" not in last and "?" not in last and "." not in last:
        parts += ["**", "*"]
    regex = ""
    for index, part in enumerate(parts):
        if part == "**":
            regex += "(?:[^/]+/)*"
            continue
        regex += re.escape(part).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        regex += "" if index == len(parts) - 1 else "/"
    return re.compile(regex + "$")


def config_inputs(root: Path, directory: str) -> list[str]:
    """The config files resolution under `directory` reads: its tsconfig chain and the workspace manifests."""
    manifests = ["pnpm-workspace.yaml", "package.json"]
    current: str | None = directory
    while current is not None:
        for name in CONFIG_NAMES:
            config = f"{current}/{name}" if current not in ("", ".") else name
            if (root / config).is_file():
                referenced = [
                    chained
                    for reference in _references(root, config)
                    for chained in _extends_chain(root, reference, depth=0)
                ]
                return [*_extends_chain(root, config, depth=0), *referenced, *manifests]
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return manifests


def _load_project(root: Path, config: str) -> _TsProject:
    key = (str(root / config), _mtime(root / config))
    cached = _PROJECT_CACHE.get(key)
    if cached is not None:
        return cached
    aliases: dict[str, tuple[str, ...]] = {}
    aliases_dir = base_url = None
    # `${configDir}` in any config of the chain means the project being resolved.
    project_dir = str(PurePosixPath(config).parent)
    for chain_config in _extends_chain(root, config, depth=0):
        options = _read_json(root / chain_config).get("compilerOptions") or {}
        config_dir = str(PurePosixPath(chain_config).parent)
        if isinstance(options.get("baseUrl"), str):
            base_url = _join(config_dir, _config_dir(options["baseUrl"], config_dir, project_dir))
        if isinstance(options.get("paths"), dict):
            aliases, aliases_dir = options["paths"], config_dir
    base = base_url if base_url is not None else aliases_dir or ""
    project = _TsProject(_rebase_aliases(aliases, base, project_dir), base_url)
    _PROJECT_CACHE[key] = project
    return project


def _config_dir(value: str, base: str, project_dir: str) -> str:
    # Rewritten relative to `base`, the folder the caller joins it onto.
    if not value.startswith(CONFIG_DIR):
        return value
    target = _join(project_dir, value[len(CONFIG_DIR) :]) or ""
    depth = len([part for part in base.split("/") if part not in ("", ".")])
    return "/".join([".."] * depth + ([target] if target else [])) or "."


def _rebase_aliases(
    aliases: dict[str, Any], base: str, project_dir: str
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    rebased: list[tuple[str, tuple[str, ...]]] = []
    for pattern, replacements in aliases.items():
        if not isinstance(replacements, list):
            continue
        joined = (
            _join(base, _config_dir(target, base, project_dir))
            for target in replacements
            if isinstance(target, str)
        )
        rebased.append((pattern, tuple(target for target in joined if target is not None)))
    # TypeScript prefers an exact pattern, then the longest prefix before `*`.
    rebased.sort(key=lambda item: ("*" in item[0], -len(item[0].partition("*")[0])))
    return tuple(rebased)


def _extends_chain(root: Path, config: str, *, depth: int) -> list[str]:
    if depth > EXTENDS_DEPTH_LIMIT:
        return [config]
    raw = _read_json(root / config).get("extends")
    parents = raw if isinstance(raw, list) else [raw]
    chain: list[str] = []
    for parent in parents:
        if not isinstance(parent, str):
            continue
        target = (
            _join(str(PurePosixPath(config).parent), parent)
            if parent.startswith(".")
            else _workspace_preset(root, parent)
        )
        if target is not None and not target.endswith(".json"):
            target += ".json"
        if target is not None and (root / target).is_file():
            chain.extend(_extends_chain(root, target, depth=depth + 1))
    return [*chain, config]


def _workspace_preset(root: Path, specifier: str) -> str | None:
    # A preset from node_modules (`expo/tsconfig.base`) is not in the repo.
    name, subpath = _split_package(specifier)
    package_dir = _workspace_packages(root).get(name)
    if package_dir is None:
        return None
    return _join(package_dir, "tsconfig.json" if subpath == "." else subpath)


def _resolve_workspace_package(root: Path, specifier: str) -> str | None:
    name, subpath = _split_package(specifier)
    package_dir = _workspace_packages(root).get(name)
    if package_dir is None:
        return None
    manifest = _read_json(root / package_dir / "package.json")
    exported = _export_targets(manifest.get("exports"), subpath)
    if exported:
        return _probe_targets(root, package_dir, exported)
    if subpath != ".":
        rest = subpath[2:]
        return _probe(root, f"{package_dir}/{rest}") or _probe(root, f"{package_dir}/src/{rest}")
    for field in ("types", "typings", "module", "main"):
        joined = _join(package_dir, str(manifest.get(field) or "")) if manifest.get(field) else None
        hit = _probe(root, joined) if joined else None
        if hit:
            return hit
    return _probe(root, f"{package_dir}/src/index") or _probe(root, f"{package_dir}/index")


def _split_package(specifier: str) -> tuple[str, str]:
    parts = specifier.split("/")
    name_length = 2 if specifier.startswith("@") else 1
    rest = "/".join(parts[name_length:])
    return "/".join(parts[:name_length]), f"./{rest}" if rest else "."


def _resolve_subpath_import(root: Path, importer: str, specifier: str) -> str | None:
    package = nearest_package(root, str(PurePosixPath(importer).parent))
    if package is None:
        return None
    manifest = _read_json(root / package[0] / "package.json")
    return _probe_targets(root, package[0], _export_targets(manifest.get("imports"), specifier))


def _probe_targets(root: Path, package_dir: str, targets: list[str]) -> str | None:
    for target in targets:
        joined = _join(package_dir, target)
        hit = _probe(root, joined) if joined is not None else None
        if hit:
            return hit
    return None


def _export_targets(exports: Any, subpath: str) -> list[str]:
    # `exports` keys start with `.`, `imports` keys with `#`; neither is a bare condition map.
    if isinstance(exports, str):
        return [exports] if subpath == "." else []
    if not isinstance(exports, dict):
        return []
    if not any(str(key).startswith((".", "#")) for key in exports):
        return _condition_values(exports) if subpath == "." else []
    if subpath in exports:
        return _condition_values(exports[subpath])
    for pattern, value in exports.items():
        captured = _match_pattern(str(pattern), subpath) if "*" in str(pattern) else None
        if captured is not None:
            return [target.replace("*", captured, 1) for target in _condition_values(value)]
    return []


def _condition_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [hit for item in value for hit in _condition_values(item)]
    if not isinstance(value, dict):
        return []
    return [
        hit for condition in EXPORT_CONDITIONS for hit in _condition_values(value.get(condition))
    ]


def _workspace_packages(root: Path) -> dict[str, str]:
    manifests = (root / "pnpm-workspace.yaml", root / "package.json")
    key = (str(root), sum(_mtime(path) for path in manifests))
    cached = _WORKSPACE_CACHE.get(key)
    if cached is not None:
        return cached
    packages: dict[str, str] = {}
    globs = _workspace_globs(root)
    excluded = [pattern[1:].rstrip("/") for pattern in globs if pattern.startswith("!")]
    for pattern in (pattern for pattern in globs if not pattern.startswith("!")):
        for package_json in sorted(root.glob(f"{pattern.rstrip('/')}/package.json")):
            directory = package_json.parent.relative_to(root).as_posix()
            if "node_modules" in directory.split("/") or any(
                fnmatch.fnmatch(directory, negated) for negated in excluded
            ):
                continue
            name = _read_json(package_json).get("name")
            if isinstance(name, str) and name:
                packages[name] = directory
    _WORKSPACE_CACHE[key] = packages
    return packages


def _workspace_globs(root: Path) -> list[str]:
    globs: list[str] = []
    pnpm = root / "pnpm-workspace.yaml"
    if pnpm.is_file():
        try:
            globs.extend(_WORKSPACE_GLOB_RE.findall(pnpm.read_text(encoding="utf-8")))
        except OSError as exc:
            logger.debug("pnpm-workspace.yaml unreadable: %s", exc)
    declared = _read_json(root / "package.json").get("workspaces")
    if isinstance(declared, dict):
        declared = declared.get("packages")
    if isinstance(declared, list):
        globs.extend(entry for entry in declared if isinstance(entry, str))
    return globs


_PACKAGE_CACHE: dict[tuple[str, int], frozenset[str]] = {}


def nearest_package(root: Path, directory: str) -> tuple[str, frozenset[str]] | None:
    """The nearest package.json's directory and the names it depends on."""
    current: str | None = directory
    while current is not None:
        manifest = (
            root / current / "package.json" if current not in ("", ".") else root / "package.json"
        )
        if manifest.is_file():
            key = (str(manifest), _mtime(manifest))
            if key not in _PACKAGE_CACHE:
                data = _read_json(manifest)
                _PACKAGE_CACHE[key] = frozenset(
                    name
                    for field in ("dependencies", "devDependencies", "peerDependencies")
                    if isinstance(data.get(field), dict)
                    for name in data[field]
                )
            return ("" if current in ("", ".") else current), _PACKAGE_CACHE[key]
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return None


__all__ = ["alias_target", "platform_twins", "resolve"]
