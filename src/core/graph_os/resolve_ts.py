"""graph_os — resolve a TypeScript/JavaScript import specifier to the repo file it names.

Mirrors the parts of TypeScript's `bundler` resolution an index needs: relative
paths with extension and index probing (including the ESM `./x.js` → `x.ts`
convention and React Native platform variants), the nearest tsconfig/jsconfig
`paths` and `baseUrl` through relative `extends`, and workspace packages through
package.json `exports` / `types` / `main`. A specifier that names no repo file
resolves to None, and the caller keeps its external-package uid.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .toolchain import strip_json_comments

logger = logging.getLogger("graph_os.resolve_ts")

SOURCE_EXTENSIONS = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
# Metro resolves `./Button` to `Button.ios.tsx` / `Button.native.tsx` when no
# plain `Button.tsx` exists.
PLATFORM_VARIANTS = ("native", "ios", "android", "web")
PLATFORM_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")
# An ESM TypeScript import names the emitted `.js`; the source is the `.ts`.
SOURCE_FOR_EMITTED = {
    ".js": (".ts", ".tsx"),
    ".jsx": (".tsx",),
    ".mjs": (".mts",),
    ".cjs": (".cts",),
}
CONFIG_NAMES = ("tsconfig.json", "jsconfig.json")
EXTENDS_DEPTH_LIMIT = 8
EXPORT_CONDITIONS = ("types", "import", "module", "react-native", "browser", "default", "require")

_WORKSPACE_GLOB_RE = re.compile(r"^\s*-\s*['\"]?([^'\"#\s]+)['\"]?", re.MULTILINE)


@dataclass(frozen=True)
class _TsProject:
    aliases: tuple[tuple[str, tuple[str, ...]], ...]
    base_url: str | None


_PROJECT_CACHE: dict[tuple[str, int], _TsProject] = {}
_WORKSPACE_CACHE: dict[tuple[str, int], dict[str, str]] = {}


def resolve(importer: str, specifier: str, root: Path) -> str | None:
    """Repo-relative path of the file `specifier` names from `importer`, or None."""
    if specifier.startswith("."):
        base = _join(str(PurePosixPath(importer).parent), specifier)
        return _probe(root, base) if base is not None else None
    project = _nearest_project(root, str(PurePosixPath(importer).parent))
    for target in _alias_targets(project, specifier, include_base_url=True):
        hit = _probe(root, target)
        if hit:
            return hit
    return _resolve_workspace_package(root, specifier)


def alias_target(importer: str, specifier: str, root: Path) -> str | None:
    """First explicit `paths` substitution for `specifier`, whether or not the file exists."""
    project = _nearest_project(root, str(PurePosixPath(importer).parent))
    return next(iter(_alias_targets(project, specifier, include_base_url=False)), None)


def _probe(root: Path, base: str) -> str | None:
    for candidate in _candidates(base):
        if (root / candidate).is_file():
            return candidate
    return None


def _candidates(base: str) -> list[str]:
    suffix = PurePosixPath(base).suffix
    stem = base[: -len(suffix)] if suffix in SOURCE_FOR_EMITTED else None
    sources = [stem + ext for ext in SOURCE_FOR_EMITTED.get(suffix, ())] if stem else []
    plain = [base, *(base + ext for ext in SOURCE_EXTENSIONS)]
    platform = [
        f"{base}.{variant}{ext}" for variant in PLATFORM_VARIANTS for ext in PLATFORM_EXTENSIONS
    ]
    index = [f"{base}/index{ext}" for ext in SOURCE_EXTENSIONS]
    return [*sources, *plain, *platform, *index]


def _join(directory: str, relative: str) -> str | None:
    parts: list[str] = []
    for part in f"{directory}/{relative}".split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


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


def _nearest_project(root: Path, directory: str) -> _TsProject | None:
    current: str | None = directory
    while current is not None:
        for name in CONFIG_NAMES:
            config = f"{current}/{name}" if current not in ("", ".") else name
            if (root / config).is_file():
                return _load_project(root, config)
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return None


def config_inputs(root: Path, directory: str) -> list[str]:
    """The config files resolution under `directory` reads: its tsconfig chain and the workspace manifests."""
    manifests = ["pnpm-workspace.yaml", "package.json"]
    current: str | None = directory
    while current is not None:
        for name in CONFIG_NAMES:
            config = f"{current}/{name}" if current not in ("", ".") else name
            if (root / config).is_file():
                return [*_extends_chain(root, config, depth=0), *manifests]
        current = None if current in ("", ".") else str(PurePosixPath(current).parent)
    return manifests


def _load_project(root: Path, config: str) -> _TsProject:
    key = (str(root / config), _mtime(root / config))
    cached = _PROJECT_CACHE.get(key)
    if cached is not None:
        return cached
    aliases: dict[str, tuple[str, ...]] = {}
    aliases_dir = base_url = None
    for chain_config in _extends_chain(root, config, depth=0):
        options = _read_json(root / chain_config).get("compilerOptions") or {}
        config_dir = str(PurePosixPath(chain_config).parent)
        if isinstance(options.get("baseUrl"), str):
            base_url = _join(config_dir, options["baseUrl"])
        if isinstance(options.get("paths"), dict):
            aliases, aliases_dir = options["paths"], config_dir
    project = _TsProject(_rebase_aliases(aliases, base_url or aliases_dir or ""), base_url)
    _PROJECT_CACHE[key] = project
    return project


def _rebase_aliases(aliases: dict[str, Any], base: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    rebased: list[tuple[str, tuple[str, ...]]] = []
    for pattern, replacements in aliases.items():
        if not isinstance(replacements, list):
            continue
        joined = (_join(base, target) for target in replacements if isinstance(target, str))
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
        if not isinstance(parent, str) or not parent.startswith("."):
            continue  # a package preset (`expo/tsconfig.base`) lives in node_modules
        target = _join(str(PurePosixPath(config).parent), parent)
        if target is not None and not target.endswith(".json"):
            target += ".json"
        if target is not None and (root / target).is_file():
            chain.extend(_extends_chain(root, target, depth=depth + 1))
    return [*chain, config]


def _resolve_workspace_package(root: Path, specifier: str) -> str | None:
    name, subpath = _split_package(specifier)
    package_dir = _workspace_packages(root).get(name)
    if package_dir is None:
        return None
    manifest = _read_json(root / package_dir / "package.json")
    exported = _export_target(manifest.get("exports"), subpath)
    if exported is not None:
        joined = _join(package_dir, exported)
        return _probe(root, joined) if joined is not None else None
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


def _export_target(exports: Any, subpath: str) -> str | None:
    if isinstance(exports, str):
        return exports if subpath == "." else None
    if not isinstance(exports, dict):
        return None
    if not any(str(key).startswith(".") for key in exports):
        return _condition_value(exports) if subpath == "." else None
    if subpath in exports:
        return _condition_value(exports[subpath])
    for pattern, value in exports.items():
        captured = _match_pattern(str(pattern), subpath) if "*" in str(pattern) else None
        target = _condition_value(value) if captured is not None else None
        if target is not None:
            return target.replace("*", captured or "", 1)
    return None


def _condition_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((hit for item in value if (hit := _condition_value(item))), None)
    if not isinstance(value, dict):
        return None
    for condition in EXPORT_CONDITIONS:
        hit = _condition_value(value.get(condition))
        if hit:
            return hit
    return None


def _workspace_packages(root: Path) -> dict[str, str]:
    manifests = (root / "pnpm-workspace.yaml", root / "package.json")
    key = (str(root), sum(_mtime(path) for path in manifests))
    cached = _WORKSPACE_CACHE.get(key)
    if cached is not None:
        return cached
    packages: dict[str, str] = {}
    for pattern in _workspace_globs(root):
        for package_json in sorted(root.glob(f"{pattern.rstrip('/')}/package.json")):
            name = _read_json(package_json).get("name")
            if isinstance(name, str) and name:
                packages[name] = package_json.parent.relative_to(root).as_posix()
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
    return [pattern for pattern in globs if not pattern.startswith("!")]


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(strip_json_comments(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        logger.debug("unreadable JSON config %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


__all__ = ["alias_target", "resolve"]
