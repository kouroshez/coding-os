"""File-based routes: Next.js, Expo Router and Astro, plus TanStack Router's declared paths.

The URL is the file's place under its router's directory, read against the
nearest package.json, which says which router the package runs: a `pages/`
folder in a package without `next` is only a folder, an Expo `app/` file is a
screen (a deep link) or a `+api` endpoint, and an Astro `src/pages/` file is a
page or an endpoint. TanStack Router writes the path in `createFileRoute('/path')`.
Without a repo root (a bare extract) the Next.js reading stands as it was.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .. import resolve_ts
from ..toolchain import get_active
from ._contracts_js import _scan_nextjs
from ._contracts_shared import ContractMatch, _line_of
from ._ts_uids import function_uid

_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "ALL")
_EXPORTED_METHOD_RE = re.compile(
    rf"""^\s*export\s+(?:async\s+)?(?:function\s+|(?:const|let)\s+)(?P<method>{"|".join(_METHODS)})\b""",
    re.MULTILINE,
)
_DEFAULT_FUNCTION_RE = re.compile(
    r"^\s*export\s+default\s+(?:async\s+)?function\s+(?P<name>\w+)", re.MULTILINE
)
_DEFAULT_EXPORT_RE = re.compile(r"^\s*export\s+default\b", re.MULTILINE)
_STATIC_PATHS_RE = re.compile(
    r"^\s*export\s+(?:async\s+)?(?:function\s+|const\s+)getStaticPaths\b", re.MULTILINE
)
_TANSTACK_RE = re.compile(r"""create(?:Lazy)?FileRoute\(\s*['"](?P<path>[^'"]+)['"]\s*\)""")
_COMPONENT_RE = re.compile(r"\bcomponent\s*:\s*(?P<name>[A-Za-z_$][\w$]*)")
_PLATFORM_SUFFIXES = (".ios", ".android", ".web", ".native")
_SCRIPT_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts")


def scan_file_routes(content: str, *, path: str) -> list[ContractMatch]:
    hits = _tanstack(content, path)
    package = _package(path)
    if package is None:
        return hits + _scan_nextjs(content, path=path)
    package_dir, dependencies = package
    relative = path[len(package_dir) + 1 :] if package_dir else path
    if "next" in dependencies:
        hits += _scan_nextjs(content, path=relative)
    if "expo-router" in dependencies:
        hits += _expo(content, relative, path)
    if "astro" in dependencies:
        hits += _astro(content, relative, path)
    return hits


def _package(path: str) -> tuple[str, frozenset[str]] | None:
    context = get_active()
    if context is None or not context.repo_root:
        return None
    return resolve_ts.nearest_package(Path(context.repo_root), str(PurePosixPath(path).parent))


def _tanstack(content: str, path: str) -> list[ContractMatch]:
    match = _TANSTACK_RE.search(content)
    if match is None:
        return []
    component = _COMPONENT_RE.search(content, match.end())
    return [
        _route(
            "tanstack-router",
            "get",
            match.group("path"),
            component.group("name") if component else None,
            path,
            _line_of(content, match.start()),
        )
    ]


def _expo(content: str, relative: str, path: str) -> list[ContractMatch]:
    segments = _under(relative, ("app", "src/app"))
    if segments is None:
        return []
    stem = _stem(segments[-1])
    if stem.endswith("+api"):
        url = _url([*segments[:-1], stem[: -len("+api")]])
        return _endpoints("expo-router", content, url, path)
    default = _DEFAULT_EXPORT_RE.search(content)
    if stem.startswith(("_", "+")) or default is None:
        return []  # layouts, +not-found / +html, and modules that render nothing
    screen = _DEFAULT_FUNCTION_RE.search(content)
    line = _line_of(content, (screen or default).start())
    url = _url([*segments[:-1], stem])
    return [_route("expo-router", "get", url, screen.group("name") if screen else None, path, line)]


def _astro(content: str, relative: str, path: str) -> list[ContractMatch]:
    segments = _under(relative, ("src/pages",))
    if segments is None or segments[-1].startswith("_"):
        return []
    last = segments[-1]
    if last.endswith(_SCRIPT_EXTENSIONS):
        return _endpoints("astro", content, _url([*segments[:-1], last.rsplit(".", 1)[0]]), path)
    if not last.endswith(".astro"):
        return []
    static_paths = _STATIC_PATHS_RE.search(content)
    handler = "getStaticPaths" if static_paths else None
    return [_route("astro", "get", _url([*segments[:-1], _stem(last)]), handler, path, 1)]


def _endpoints(framework: str, content: str, url: str, path: str) -> list[ContractMatch]:
    return [
        _route(
            framework,
            match.group("method").lower(),
            url,
            match.group("method"),
            path,
            _line_of(content, match.start()),
        )
        for match in _EXPORTED_METHOD_RE.finditer(content)
    ]


def _route(
    framework: str, method: str, url: str, handler: str | None, path: str, line: int
) -> ContractMatch:
    extra = (("handler_uid", function_uid(path, handler)),) if handler else ()
    return ContractMatch(
        kind="http",
        framework=framework,
        method=method,
        path=url,
        handler=handler,
        line=line,
        extra=(*extra, ("syntax_tree", True)),
    )


def _under(relative: str, roots: tuple[str, ...]) -> list[str] | None:
    for root in roots:
        if relative.startswith(f"{root}/"):
            return relative[len(root) + 1 :].split("/")
    return None


def _stem(name: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    for suffix in _PLATFORM_SUFFIXES:
        stem = stem.removesuffix(suffix)
    return stem


def _url(segments: list[str]) -> str:
    pieces = []
    for segment in segments:
        if segment.startswith("(") and segment.endswith(")"):
            continue  # an Expo route group names no URL segment
        if segment == "index":
            continue
        pieces.append(
            "{" + segment[1:-1] + "}"
            if segment.startswith("[") and segment.endswith("]")
            else segment
        )
    return "/" + "/".join(pieces)
