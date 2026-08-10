"""Python web-framework contract scanners — FastAPI, Flask, DRF, Django URLs.

One ecosystem per module: a new FastAPI decorator shape should never put the Go
or TypeScript scanners in the diff.
"""

from __future__ import annotations

import re

from ._contracts_shared import (
    _STRING_CAPTURE,
    ContractMatch,
    _line_of,
    _next_def_name,
    _parse_method_list,
)

# FastAPI: @app.get("/x"), @router.post("/x"), app.include_router(..., prefix="/v2")
_FASTAPI_ROUTE_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.(?P<method>get|post|put|patch|delete|head|options|trace)
        \s*\(\s*{_STRING_CAPTURE}
    """,
    re.VERBOSE,
)
_FASTAPI_INCLUDE_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.include_router\s*\([^)]*?prefix\s*=\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# Flask: @app.route("/x", methods=["POST"]) | @blueprint.route(...)
_FLASK_ROUTE_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.route\s*\(\s*{_STRING_CAPTURE}
        (?:[^)]*?methods\s*=\s*\[(?P<methods>[^\]]+)\])?
    """,
    re.VERBOSE,
)

# Django DRF: @api_view(['GET']); router.register(prefix, ViewSetClass)
_DRF_API_VIEW_RE = re.compile(
    r"""@api_view\s*\(\s*\[(?P<methods>[^\]]+)\]\s*\)\s*\n\s*def\s+(?P<handler>[A-Za-z_][\w]*)""",
    re.VERBOSE,
)
_DRF_ROUTER_REGISTER_RE = re.compile(
    rf"""(?P<router>[A-Za-z_][\w.]*)\.register\s*\(\s*{_STRING_CAPTURE}\s*,\s*
        (?P<viewset>[A-Za-z_][\w.]*)
    """,
    re.VERBOSE,
)

# Django classic urlpatterns: path("x", view, name="x"), re_path(r"...", ...)
_DJANGO_URL_RE = re.compile(
    rf"""(?:path|re_path)\s*\(\s*
        (?:r?{_STRING_CAPTURE})\s*,\s*
        (?P<handler>[A-Za-z_][\w.]*)
    """,
    re.VERBOSE,
)


def _scan_fastapi(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _FASTAPI_ROUTE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="http",
                framework="fastapi",
                method=match.group("method").lower(),
                path=match.group("path"),
                handler=_next_def_name(content, match.end()),
                line=_line_of(content, match.start()),
            )
        )
    for match in _FASTAPI_INCLUDE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="http",
                framework="fastapi",
                method="mount",
                path=match.group("path"),
                handler=None,
                line=_line_of(content, match.start()),
                confidence=0.75,
                derivation="fastapi_include_router",
            )
        )
    return hits


def _scan_flask(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _FLASK_ROUTE_RE.finditer(content):
        methods_raw = match.group("methods") or "GET"
        for method in _parse_method_list(methods_raw):
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="flask",
                    method=method.lower(),
                    path=match.group("path"),
                    handler=_next_def_name(content, match.end()),
                    line=_line_of(content, match.start()),
                )
            )
    return hits


def _scan_drf(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _DRF_API_VIEW_RE.finditer(content):
        for method in _parse_method_list(match.group("methods")):
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="drf",
                    method=method.lower(),
                    path=f"<api_view:{match.group('handler')}>",
                    handler=match.group("handler"),
                    line=_line_of(content, match.start()),
                )
            )
    for match in _DRF_ROUTER_REGISTER_RE.finditer(content):
        prefix = match.group("path").strip("/")
        viewset = match.group("viewset")
        line = _line_of(content, match.start())
        for method, suffix in (
            ("get", "/"),
            ("post", "/"),
            ("get", "/{pk}/"),
            ("put", "/{pk}/"),
            ("patch", "/{pk}/"),
            ("delete", "/{pk}/"),
        ):
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="drf",
                    method=method,
                    path=f"/{prefix}{suffix}",
                    handler=viewset,
                    line=line,
                    confidence=0.9,
                    derivation="drf_router_register",
                )
            )
    return hits


def _scan_django_urlpatterns(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _DJANGO_URL_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="http",
                framework="django",
                method="any",
                path=match.group("path"),
                handler=match.group("handler"),
                line=_line_of(content, match.start()),
                confidence=0.88,
            )
        )
    return hits
