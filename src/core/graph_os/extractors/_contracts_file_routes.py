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
# `export default X`, or the re-export `export { default } from './Screen'`.
_DEFAULT_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\b|\{[^}]*\bdefault\b[^}]*\})", re.MULTILINE
)
_DEFAULT_NAME_RE = re.compile(
    r"^\s*export\s+default\s+(?P<name>[A-Za-z_$][\w$]*)\s*;?\s*$", re.MULTILINE
)
# `export { handle as POST }` names a method as surely as `export const POST`.
_EXPORT_CLAUSE_RE = re.compile(r"^\s*export\s*\{(?P<names>[^}]*)\}\s*;?\s*$", re.MULTILINE)
_PARAM_RE = re.compile(r"\[([^\[\]]+)\]")
_PAGE_EXTENSIONS = (".astro", ".md", ".mdx", ".html")
# TanStack code routes: `const x = createRoute({ getParentRoute: () => p, path: 'posts', … })`.
_CODE_ROUTE_RE = re.compile(
    r"(?:const|let)\s+(?P<var>[\w$]+)\s*=\s*createRoute\(\s*\{(?P<body>[^{}]*)\}"
)
_CODE_ROUTE_PARENT_RE = re.compile(r"getParentRoute\s*:\s*\(\s*\)\s*=>\s*(?P<parent>[\w$]+)")
_CODE_ROUTE_PATH_RE = re.compile(r"""\bpath\s*:\s*['"](?P<path>[^'"]*)['"]""")
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


def scan_markdown_page(content: str, *, path: str) -> list[ContractMatch]:
    """An Astro page written in Markdown; no other scanner reads prose."""
    package = _package(path)
    if package is None or "astro" not in package[1]:
        return []
    relative = path[len(package[0]) + 1 :] if package[0] else path
    return _astro(content, relative, path)


def _tanstack(content: str, path: str) -> list[ContractMatch]:
    match = _TANSTACK_RE.search(content)
    if match is None:
        return _tanstack_code_routes(content, path)
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


def _tanstack_code_routes(content: str, path: str) -> list[ContractMatch]:
    # A code route's path is relative to its parent's; compose up the chain.
    routes: dict[str, tuple[str | None, str, str | None, int]] = {}
    for match in _CODE_ROUTE_RE.finditer(content):
        body = match.group("body")
        parent, own = _CODE_ROUTE_PARENT_RE.search(body), _CODE_ROUTE_PATH_RE.search(body)
        component = _COMPONENT_RE.search(body)
        routes[match.group("var")] = (
            parent.group("parent") if parent else None,
            own.group("path") if own else "",
            component.group("name") if component else None,
            _line_of(content, match.start()),
        )
    hits = []
    for variable, (_, _, component_name, line) in routes.items():
        segments: list[str] = []
        current: str | None = variable
        for _ in range(len(routes) + 1):
            if current not in routes:
                break
            parent, own, _, _ = routes[current]
            segments.append(own.strip("/"))
            current = parent
        url = "/" + "/".join(segment for segment in reversed(segments) if segment)
        hits.append(_route("tanstack-router", "get", url, component_name, path, line))
    return hits


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
    screen = _DEFAULT_FUNCTION_RE.search(content) or _DEFAULT_NAME_RE.search(content)
    line = _line_of(content, (screen or default).start())
    url = _url([*segments[:-1], stem])
    return [_route("expo-router", "get", url, screen.group("name") if screen else None, path, line)]


def _astro(content: str, relative: str, path: str) -> list[ContractMatch]:
    segments = _under(relative, ("src/pages",))
    # Astro builds no route from a file or folder whose name starts with `_`.
    if segments is None or any(segment.startswith("_") for segment in segments):
        return []
    last = segments[-1]
    if last.endswith(_SCRIPT_EXTENSIONS):
        return _endpoints("astro", content, _url([*segments[:-1], last.rsplit(".", 1)[0]]), path)
    if not last.endswith(_PAGE_EXTENSIONS):
        return []
    static_paths = _STATIC_PATHS_RE.search(content)
    handler = "getStaticPaths" if static_paths else None
    return [_route("astro", "get", _url([*segments[:-1], _stem(last)]), handler, path, 1)]


def _endpoints(framework: str, content: str, url: str, path: str) -> list[ContractMatch]:
    hits = [
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
    for match in _EXPORT_CLAUSE_RE.finditer(content):
        for entry in match.group("names").split(","):
            local, _, exported = (part.strip() for part in entry.partition(" as "))
            if exported in _METHODS:
                line = _line_of(content, match.start())
                hits.append(_route(framework, exported.lower(), url, local, path, line))
    return hits


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
        # `[id]`, `[a]-[b]` and `[id].json` alike: every bracket is a parameter.
        pieces.append(_PARAM_RE.sub(r"{\1}", segment))
    return "/" + "/".join(pieces)
