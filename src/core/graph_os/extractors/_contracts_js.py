"""TypeScript/JavaScript contract scanners — Next.js routes, NestJS, emitters."""

from __future__ import annotations

import re

from ._contracts_shared import _STRING_CAPTURE, ContractMatch, _join_paths, _line_of
from .md_links import _normalize_path

# Next.js route.ts + page.ts: `export async function GET(` / `export function POST(`
_NEXTJS_ROUTE_RE = re.compile(
    r"""^\s*export\s+(?:async\s+)?function\s+
        (?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
# pages-router handler / page = a default export (function, arrow, or
# reference). Used to detect pages/api/** handlers and page components.
_NEXTJS_DEFAULT_EXPORT_RE = re.compile(
    r"""^\s*export\s+default\b""",
    re.VERBOSE | re.MULTILINE,
)

# NestJS: @Controller('/x'), @Get('/y')
_NEST_METHOD_RE = re.compile(
    rf"""@(?P<method>Get|Post|Put|Patch|Delete)\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
_NEST_CONTROLLER_RE = re.compile(rf"""@Controller\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE)

# Node.js EventEmitter / browser DOM: `<emitter>.addEventListener("evt", fn)`,
# `<emitter>.on("evt", fn)` in TS/JS files.
_TS_EMITTER_ON_RE = re.compile(
    rf"""(?P<emitter>[A-Za-z_$][\w$.]*)\.(?:on|addEventListener)\s*\(\s*{_STRING_CAPTURE}\s*,\s*
        (?P<handler>[A-Za-z_$][\w$]*|\([^)]*\)\s*=>)
    """,
    re.VERBOSE,
)


_NEXTJS_PAGE_FILES = {"page.tsx", "page.ts", "page.jsx", "page.js"}


def _scan_nextjs(content: str, *, path: str) -> list[ContractMatch]:
    """Detect Next.js routes — app-router handlers + pages-router + page components.

    Three shapes:
      1. app-router route handlers — named `export function GET(...)` in
         `route.ts(x)` (per HTTP method).
      2. pages-router API — `pages/api/**` with a default-export handler
         (method `any`).
      3. page routes — `app/**/page.tsx` or any `pages/**` page file with a
         default export is itself a `GET` route at the derived URL.
    Gated on the file living under `app/` or `pages/` so ordinary
    components never become phantom routes.
    """
    hits: list[ContractMatch] = []
    norm = _normalize_path(path)
    parts = norm.split("/")
    in_app = "app" in parts
    in_pages = "pages" in parts
    if not in_app and not in_pages:
        return hits

    url = _nextjs_route_path(path)
    note = "dynamic_segment" if _has_dynamic_segment(path) else None
    fname = parts[-1] if parts else ""

    # 1. App-router route handlers (named method exports).
    matched_app_route = False
    for match in _NEXTJS_ROUTE_RE.finditer(content):
        matched_app_route = True
        hits.append(
            ContractMatch(
                kind="http",
                framework="nextjs",
                method=match.group("method").lower(),
                path=url,
                handler=None,
                line=_line_of(content, match.start()),
                note=note,
            )
        )
    if matched_app_route:
        return hits

    default_export = _NEXTJS_DEFAULT_EXPORT_RE.search(content)
    if default_export is None:
        return hits
    line = _line_of(content, default_export.start())

    # 2. pages-router API route — default-export handler under pages/api/**.
    if in_pages and "api" in parts:
        hits.append(
            ContractMatch(
                kind="http",
                framework="nextjs",
                method="any",
                path=url,
                handler=None,
                line=line,
                confidence=0.85,
                derivation="pages_router_api",
                note=note,
            )
        )
        return hits

    # 3. page route — the page component is a GET route at the derived URL.
    is_app_page = in_app and fname in _NEXTJS_PAGE_FILES
    is_pages_page = in_pages and not fname.startswith("_")
    if is_app_page or is_pages_page:
        hits.append(
            ContractMatch(
                kind="http",
                framework="nextjs",
                method="get",
                path=url,
                handler=None,
                line=line,
                confidence=0.8,
                derivation="nextjs_page",
                note=note,
            )
        )
    return hits


def _scan_nest(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    controller_path = ""
    ctrl_match = _NEST_CONTROLLER_RE.search(content)
    if ctrl_match:
        controller_path = ctrl_match.group("path")
    for match in _NEST_METHOD_RE.finditer(content):
        route = _join_paths(controller_path, match.group("path"))
        hits.append(
            ContractMatch(
                kind="http",
                framework="nestjs",
                method=match.group("method").lower(),
                path=route,
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_ts_emitter(content: str) -> list[ContractMatch]:
    """R4: TS `<emitter>.on('evt', fn)` / `addEventListener('evt', fn)`.

    Narrowed to emitter names containing 'bus', 'emitter', 'events' or
    DOM-side `addEventListener` so we don't false-match generic .on().
    """
    hits: list[ContractMatch] = []
    for match in _TS_EMITTER_ON_RE.finditer(content):
        emitter = match.group("emitter")
        event_name = match.group("path")
        tail = emitter.split(".")[-1].lower()
        # `addEventListener` always passes through; for `on` we gate on tail.
        if "addEventListener" not in match.group(0):
            if tail not in {"bus", "events", "emitter", "pubsub", "channel"}:
                continue
        hits.append(
            ContractMatch(
                kind="event",
                framework="ts_emitter",
                method="on",
                path=f"{emitter}:{event_name}",
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _nextjs_route_path(file_path: str) -> str:
    """Turn a Next.js file path into its URL.

    app-router: `app/users/[id]/route.ts` → `/users/{id}` (the route/page
    file is dropped; the directory IS the URL).
    pages-router: `pages/api/users.ts` → `/api/users`, `pages/index.tsx` →
    `/`, `pages/blog/[slug].tsx` → `/blog/{slug}` (the file IS the route, so
    strip its extension and collapse `index`).
    """
    normalised = _normalize_path(file_path)
    parts = normalised.split("/")
    router = None
    idx = -1
    for candidate in ("app", "pages"):
        if candidate in parts:
            idx = parts.index(candidate)
            router = candidate
            break
    if router is None:
        return normalised
    segments = parts[idx + 1 :]
    if router == "app":
        if segments and segments[-1] in (
            "route.ts",
            "route.tsx",
            "route.js",
            "route.jsx",
            "page.ts",
            "page.tsx",
            "page.js",
            "page.jsx",
        ):
            segments = segments[:-1]
    elif segments:  # pages-router — the file itself is the route
        last = segments[-1]
        stem = last.rsplit(".", 1)[0] if "." in last else last
        segments = segments[:-1] if stem == "index" else [*segments[:-1], stem]
    pieces: list[str] = []
    for seg in segments:
        if seg.startswith("[[") and seg.endswith("]]"):
            pieces.append("**" + seg[3:-2])
        elif seg.startswith("[") and seg.endswith("]"):
            pieces.append("{" + seg[1:-1] + "}")
        else:
            pieces.append(seg)
    route = "/" + "/".join(pieces)
    return route or "/"


def _has_dynamic_segment(path: str) -> bool:
    return "[" in path
