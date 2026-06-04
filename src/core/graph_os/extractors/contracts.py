"""graph_os — service contracts extractor (I.7).

DEPENDS:  stdlib only.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.contracts")
EXTRACTOR_ID = "contracts@v1"


@dataclass(frozen=True)
class ContractMatch:
    kind: str  # "http" | "mcp" | "grpc" | "event" | "websocket" | "cli"
    framework: str  # "fastapi", "drf", "flask", "django", "celery", ...
    method: str  # HTTP method or event name or "rpc"
    path: str  # raw specifier
    handler: str | None  # best-guess function / class symbol
    line: int
    note: str | None = None
    confidence: float = 0.9
    derivation: str | None = None  # e.g. "drf_router_register"


# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------


_STRING_CAPTURE = r"""['"](?P<path>[^'"]+)['"]"""
_STRING_METHOD = r"""['"](?P<method>[^'"]+)['"]"""

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

# Go Fiber: app.Get("/x", handler), app.Group("/v1")
_FIBER_ROUTE_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.(?P<method>Get|Post|Put|Patch|Delete|Head|Options|All)
        \s*\(\s*{_STRING_CAPTURE}
    """,
    re.VERBOSE,
)
_FIBER_GROUP_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.Group\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# Go Gin: r.GET("/x", handler), v1 := r.Group("/v1")
_GIN_ROUTE_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Any)
        \s*\(\s*{_STRING_CAPTURE}
    """,
    re.VERBOSE,
)
_GIN_GROUP_RE = re.compile(
    rf"""(?:[A-Za-z_]\w*\s*:?=\s*)?(?P<app>[A-Za-z_][\w.]*)\.Group\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# Shared across fiber/gin/echo: `v1 := app.Group("/api")` — captures the
# assigned variable so a route registered on THAT variable gets THAT
# group's prefix (fixes the "last group seen prefixes every route" bug).
_GO_GROUP_ASSIGN_RE = re.compile(
    rf"""(?P<var>[A-Za-z_]\w*)\s*:?=\s*(?P<app>[A-Za-z_][\w.]*)\.Group\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
# The handler is the first identifier argument after the route path string:
# `app.Get("/x", handlers.List)` → `handlers.List`. Inline funcs / no second
# arg yield no handler.
_GO_ROUTE_HANDLER_RE = re.compile(r"""\s*,\s*(?P<handler>[A-Za-z_][\w.]*)""", re.VERBOSE)

# Go Echo: e.GET("/x", handler) — matches the same method-case as Gin.

# Go Chi: r.Get / r.Post / r.Route("/x", func(r chi.Router) { ... })
_CHI_ROUTE_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.(?P<method>Get|Post|Put|Patch|Delete|Head|Options|Connect|Trace|MethodFunc|HandleFunc|Handle)
        \s*\(\s*{_STRING_CAPTURE}
    """,
    re.VERBOSE,
)
_CHI_ROUTE_NEST_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.Route\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# Go gorilla/mux: r.HandleFunc("/x", handler).Methods("GET","POST")
_GORILLA_RE = re.compile(
    rf"""(?P<app>[A-Za-z_][\w.]*)\.HandleFunc\s*\(\s*{_STRING_CAPTURE}
        [^)]*\)
        (?:\s*\.Methods\(\s*"(?P<methods>[^)]+)"\s*\))?
    """,
    re.VERBOSE,
)

# Go stdlib net/http (Go 1.22+): http.HandleFunc("GET /path", h) and mux.HandleFunc
_NET_HTTP_RE = re.compile(
    r"""(?:http|[A-Za-z_]\w*)\.HandleFunc
        \s*\(\s*"(?P<pattern>(?:[A-Z]+\s+)?/[^"]*)"
    """,
    re.VERBOSE,
)

# Go gRPC service registration: pb.RegisterFooServer(s, &impl{})
_GRPC_REGISTER_RE = re.compile(
    r"""(?P<pkg>[A-Za-z_]\w*)\.Register(?P<svc>[A-Z]\w*)Server\s*\(""",
    re.VERBOSE,
)

# spf13/cobra command literal: cobra.Command{ Use: "foo", ... }
_COBRA_USE_RE = re.compile(
    rf"""cobra\.Command\s*\{{\s*[^}}]*?\bUse\s*:\s*{_STRING_CAPTURE}""",
    re.VERBOSE | re.DOTALL,
)

# urfave/cli command: &cli.Command{ Name: "foo", ... }
_URFAVE_CLI_RE = re.compile(
    rf"""cli\.Command\s*\{{\s*[^}}]*?\bName\s*:\s*{_STRING_CAPTURE}""",
    re.VERBOSE | re.DOTALL,
)

# MCP tool decorators: @mcp.tool("name"), @mcp.tool(name="x")
_MCP_TOOL_RE = re.compile(
    rf"""@(?P<server>[A-Za-z_][\w.]*)\.tool\s*\(\s*
        (?:name\s*=\s*)?{_STRING_CAPTURE}
    """,
    re.VERBOSE,
)
_MCP_SAFE_TOOL_RE = re.compile(r"@safe_tool\b")

# Celery / RQ / Channels / websockets.
_CELERY_TASK_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.task\s*(?:\([^)]*?name\s*=\s*{_STRING_CAPTURE}[^)]*\))?
        \s*\n\s*def\s+(?P<handler>[A-Za-z_][\w]*)
    """,
    re.VERBOSE,
)
_CHANNELS_RECEIVER_RE = re.compile(
    r"""@(?:receiver)\s*\(\s*[A-Za-z_][\w]*\s*,\s*sender\s*=\s*(?P<sender>[A-Za-z_][\w.]*)""",
    re.VERBOSE,
)
_WEBSOCKET_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.sock\.route\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# Dynamic hints — fetch with template literal.
_DYNAMIC_FETCH_RE = re.compile(r"fetch\s*\(\s*`[^`]*\$\{")


# R4: event-driven handler patterns — `@bus.on("event")`, `@router.subscribe`,
# `@<emitter>.subscribe`, FastAPI SSE endpoints, hook event subscribers.
# Captured kind="event" — flows into the same handles_event edge type.
_PUBSUB_ON_RE = re.compile(
    rf"""@(?P<emitter>[A-Za-z_][\w.]*)\.on\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
_PUBSUB_SUBSCRIBE_RE = re.compile(
    rf"""@(?P<emitter>[A-Za-z_][\w.]*)\.subscribe\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
# FastAPI/Starlette SSE: function returns EventSourceResponse(...) or
# yields ServerSentEvent(...) — best paired with an @app.get/@router.get
# decorator (already captured by FASTAPI_ROUTE_RE). Flag the function
# so the route node can be annotated; we promote the route from
# handles_route → handles_event via post-pass downstream.
_SSE_HINT_RE = re.compile(
    r"""(?:EventSourceResponse|ServerSentEvent|sse_starlette)\s*\(""",
    re.VERBOSE,
)
# Node.js EventEmitter / browser DOM: `<emitter>.addEventListener("evt", fn)`,
# `<emitter>.on("evt", fn)` in TS/JS files.
_TS_EMITTER_ON_RE = re.compile(
    rf"""(?P<emitter>[A-Za-z_$][\w$.]*)\.(?:on|addEventListener)\s*\(\s*{_STRING_CAPTURE}\s*,\s*
        (?P<handler>[A-Za-z_$][\w$]*|\([^)]*\)\s*=>)
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a source file for service contracts."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_doc_blob = _python_file_docstring(content) if normalised.endswith(".py") else None

    file_node = GraphNode(
        uid=f"code:file:{normalised}",
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang=_lang_for(normalised),
        doc_blob=file_doc_blob,
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    matches: list[ContractMatch] = []
    try:
        if normalised.endswith(".py"):
            matches.extend(_scan_fastapi(content))
            matches.extend(_scan_flask(content))
            matches.extend(_scan_drf(content))
            matches.extend(_scan_django_urlpatterns(content))
            matches.extend(_scan_mcp(content))
            matches.extend(_scan_celery(content))
            matches.extend(_scan_channels_signals(content))
            matches.extend(_scan_websocket(content))
            # R4: pub/sub + SSE patterns broaden handles_event surface.
            matches.extend(_scan_pubsub(content, framework_label="python"))
            matches.extend(_scan_sse(content))
        elif normalised.endswith(".ts") or normalised.endswith(".tsx"):
            matches.extend(_scan_nextjs(content, path=normalised))
            matches.extend(_scan_nest(content))
            # R4: TS-side event listeners.
            matches.extend(_scan_pubsub(content, framework_label="ts"))
            matches.extend(_scan_ts_emitter(content))
        elif normalised.endswith(".go"):
            matches.extend(_scan_fiber(content))
            matches.extend(_scan_gin(content))
            matches.extend(_scan_echo(content))
            matches.extend(_scan_chi(content))
            matches.extend(_scan_gorilla(content))
            matches.extend(_scan_net_http(content))
            matches.extend(_scan_grpc(content))
            matches.extend(_scan_cobra(content))
            matches.extend(_scan_urfave_cli(content))
        elif normalised.endswith(".php"):
            matches.extend(_scan_laravel(content))
            matches.extend(_scan_wordpress(content))
            matches.extend(_scan_whmcs(content, path=normalised))
    except Exception as exc:
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))

    if _DYNAMIC_FETCH_RE.search(content):
        result.parse_errors.append(
            ParseError(
                kind="opaque_route",
                detail="fetch() uses a template literal — target route is opaque",
            )
        )

    for hit in matches:
        _emit(file_node.uid, hit, normalised=normalised, result=result)

    # S3: Folder→...→File spine + File→Route/Tool/Event direct
    # ``contains`` edges for the tree-view. The ``handles_route`` /
    # ``handles_tool`` / ``handles_event`` edges already emitted by
    # ``_emit`` are semantic (which file owns which surface); the
    # ``contains`` edges added below are structural (tree placement).
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    for hit in matches:
        contract_uid = _contract_uid(hit)
        result.edges.append(
            GraphEdge(
                source_uid=file_node.uid,
                target_uid=contract_uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )

    _promote_stubs(result)
    return result


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


_HTTP_NOISE_PATHS = {"/x", "/y", "/z", "/foo", "/bar", "/test", "/path"}


def _looks_like_noise(match: ContractMatch) -> bool:
    if match.kind == "http":
        return match.path in _HTTP_NOISE_PATHS
    return False


def _emit(
    source_uid: str,
    match: ContractMatch,
    *,
    normalised: str,
    result: ExtractionResult,
) -> None:
    if _looks_like_noise(match):
        return
    target_uid = _contract_uid(match)
    label = _contract_label(match)
    metadata = {
        "kind": match.kind,
        "framework": match.framework,
        "method": match.method,
        "path": match.path,
        "handler": match.handler,
        "extractor": EXTRACTOR_ID,
    }
    if match.derivation:
        metadata["derivation"] = match.derivation
    if match.note:
        metadata["note"] = match.note
    result.nodes.append(
        GraphNode(
            uid=target_uid,
            kind=_node_kind(match),
            label=label,
            file_path=normalised,
            start_line=match.line,
            lang=_lang_for(normalised),
            metadata=metadata,
        )
    )
    edge_type = {
        "http": "handles_route",
        "mcp": "handles_tool",
        "grpc": "handles_tool",
        "event": "handles_event",
        "websocket": "handles_route",
        "cli": "handles_command",
    }.get(match.kind, "handles_route")

    evidence = (EvidenceSignal(f"{match.framework}_{match.kind}", match.confidence),)
    result.edges.append(
        GraphEdge(
            source_uid=source_uid,
            target_uid=target_uid,
            edge_type=edge_type,
            extractor=EXTRACTOR_ID,
            confidence=match.confidence,
            source_span=f"{normalised}:{match.line}",
            evidence=evidence,
        )
    )
    if match.handler:
        # Resolve Python handlers to the real same-file function node
        # (code_python emits it in the same reindex; _next_def_name yields
        # a def in THIS file). The old unresolved-stub target left
        # references/impact/rename empty for every route + MCP handler
        # (TASK-053). Non-.py handlers keep the stub (no same-file table).
        if normalised.endswith(".py"):
            handler_uid = f"code:function:{normalised}::{match.handler}"
        else:
            handler_uid = f"code:external:unresolved:{match.handler}"
        result.edges.append(
            GraphEdge(
                source_uid=target_uid,
                target_uid=handler_uid,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=match.confidence * 0.9,
                source_span=f"{normalised}:{match.line}",
            )
        )


def _contract_uid(match: ContractMatch) -> str:
    if match.kind == "http":
        return f"cos:route:{match.method.upper()}:{match.path}"
    if match.kind == "mcp":
        return f"cos:mcp_tool:{match.path}"
    if match.kind == "grpc":
        return f"cos:route:grpc:{match.path}"
    if match.kind == "event":
        return f"cos:route:event:{match.framework}:{match.path}"
    if match.kind == "websocket":
        return f"cos:route:ws:{match.path}"
    if match.kind == "cli":
        return f"cos:cli:{match.framework}:{match.path}"
    return f"cos:route:{match.kind}:{match.path}"


def _contract_label(match: ContractMatch) -> str:
    if match.kind == "http":
        return f"{match.method.upper()} {match.path}"
    if match.kind == "mcp":
        return f"mcp:{match.path}"
    return f"{match.framework}:{match.path}"


def _node_kind(match: ContractMatch) -> str:
    return {
        "mcp": "cos:mcp_tool",
        "http": "cos:route",
        "grpc": "cos:route",
        "event": "cos:route",
        "websocket": "cos:route",
        "cli": "cos:cli_command",
    }.get(match.kind, "cos:route")


def _lang_for(path: str) -> str:
    if path.endswith(".py"):
        return "py"
    if path.endswith(".ts"):
        return "ts"
    if path.endswith(".tsx"):
        return "tsx"
    if path.endswith(".go"):
        return "go"
    return "txt"


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------


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


_FIBER_CTX_FALSE_POS = {"c", "ctx"}  # *fiber.Ctx; .Get reads headers, not a route.


def _scan_fiber(content: str) -> list[ContractMatch]:
    if "gofiber" not in content and "fiber.App" not in content and "fiber.New" not in content:
        return []
    hits: list[ContractMatch] = []
    prefixes = _go_group_prefixes(content)
    for match in _FIBER_ROUTE_RE.finditer(content):
        app_var = match.group("app")
        if app_var.lower() in _FIBER_CTX_FALSE_POS:
            continue
        path = match.group("path")
        prefix = prefixes.get(app_var, "")
        if prefix:
            path = _join_paths(prefix, path)
        hits.append(
            ContractMatch(
                kind="http",
                framework="fiber",
                method=match.group("method").lower(),
                path=path,
                handler=_go_route_handler(content, match.end()),
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_gin(content: str) -> list[ContractMatch]:
    if "gin." not in content and "gin-gonic" not in content:
        return []
    hits: list[ContractMatch] = []
    prefixes = _go_group_prefixes(content)
    for match in _GIN_ROUTE_RE.finditer(content):
        app_var = match.group("app")
        if app_var.lower() in _FIBER_CTX_FALSE_POS:
            continue
        path = match.group("path")
        prefix = prefixes.get(app_var, "")
        if prefix:
            path = _join_paths(prefix, path)
        hits.append(
            ContractMatch(
                kind="http",
                framework="gin",
                method=match.group("method").lower(),
                path=path,
                handler=_go_route_handler(content, match.end()),
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_echo(content: str) -> list[ContractMatch]:
    if "echo." not in content and "labstack/echo" not in content:
        return []
    hits: list[ContractMatch] = []
    prefixes = _go_group_prefixes(content)
    for match in _GIN_ROUTE_RE.finditer(content):
        app_var = match.group("app")
        if app_var.lower() in _FIBER_CTX_FALSE_POS:
            continue
        path = match.group("path")
        prefix = prefixes.get(app_var, "")
        if prefix:
            path = _join_paths(prefix, path)
        hits.append(
            ContractMatch(
                kind="http",
                framework="echo",
                method=match.group("method").lower(),
                path=path,
                handler=_go_route_handler(content, match.end()),
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_chi(content: str) -> list[ContractMatch]:
    if "chi." not in content and "go-chi/chi" not in content:
        return []
    hits: list[ContractMatch] = []
    for match in _CHI_ROUTE_RE.finditer(content):
        method = match.group("method").lower()
        if method in ("handlefunc", "handle", "methodfunc"):
            method = "any"
        hits.append(
            ContractMatch(
                kind="http",
                framework="chi",
                method=method,
                path=match.group("path"),
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_gorilla(content: str) -> list[ContractMatch]:
    if "gorilla/mux" not in content and "mux.New" not in content:
        return []
    hits: list[ContractMatch] = []
    for match in _GORILLA_RE.finditer(content):
        methods_raw = match.group("methods") or ""
        methods = [m.strip().lower().strip('"') for m in methods_raw.split(",") if m.strip()]
        if not methods:
            methods = ["any"]
        for method in methods:
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="gorilla",
                    method=method,
                    path=match.group("path"),
                    handler=None,
                    line=_line_of(content, match.start()),
                )
            )
    return hits


def _scan_net_http(content: str) -> list[ContractMatch]:
    if "net/http" not in content:
        return []
    hits: list[ContractMatch] = []
    for match in _NET_HTTP_RE.finditer(content):
        pattern = match.group("pattern").strip()
        if " " in pattern:
            method_part, _, path = pattern.partition(" ")
            method = method_part.lower()
        else:
            method, path = "any", pattern
        hits.append(
            ContractMatch(
                kind="http",
                framework="net_http",
                method=method,
                path=path,
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_grpc(content: str) -> list[ContractMatch]:
    if (
        "grpc." not in content
        and "google.golang.org/grpc" not in content
        and ".RegisterServer" not in content
    ):
        return []
    hits: list[ContractMatch] = []
    for match in _GRPC_REGISTER_RE.finditer(content):
        svc = match.group("svc")
        hits.append(
            ContractMatch(
                kind="grpc",
                framework="grpc",
                method="register",
                path=svc,
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_cobra(content: str) -> list[ContractMatch]:
    if "cobra." not in content and "spf13/cobra" not in content:
        return []
    hits: list[ContractMatch] = []
    for match in _COBRA_USE_RE.finditer(content):
        use_value = match.group("path")
        cmd_name = use_value.split()[0] if use_value else use_value
        hits.append(
            ContractMatch(
                kind="cli",
                framework="cobra",
                method="command",
                path=cmd_name,
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_urfave_cli(content: str) -> list[ContractMatch]:
    if "urfave/cli" not in content and "cli.App" not in content and "cli.Command" not in content:
        return []
    hits: list[ContractMatch] = []
    for match in _URFAVE_CLI_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="cli",
                framework="urfave_cli",
                method="command",
                path=match.group("path"),
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


# ---------------------------------------------------------------------------
# PHP frameworks — Laravel / WordPress / WHMCS
# ---------------------------------------------------------------------------

# Laravel: Route::get('/x', handler). `match`/group-closure handled below.
_LARAVEL_ROUTE_RE = re.compile(
    rf"""Route::(?P<method>get|post|put|patch|delete|options|any)\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
_LARAVEL_RESOURCE_RE = re.compile(
    rf"""Route::(?P<kind>apiResource|resource)\s*\(\s*{_STRING_CAPTURE}\s*,\s*
        (?P<ctrl>[A-Za-z_\\][\w\\]*)::class
    """,
    re.VERBOSE,
)
# Handler arg right after the route path string.
_LARAVEL_H_ARRAY_RE = re.compile(
    r"""^\s*,\s*\[\s*(?P<ctrl>[A-Za-z_\\][\w\\]*)::class\s*,\s*['"](?P<method>\w+)['"]"""
)
_LARAVEL_H_STRING_RE = re.compile(r"""^\s*,\s*['"](?P<ctrl>[A-Za-z_\\][\w]*)@(?P<method>\w+)['"]""")
_LARAVEL_H_INVOKE_RE = re.compile(r"""^\s*,\s*(?P<ctrl>[A-Za-z_\\][\w\\]*)::class\s*[\),]""")
_LARAVEL_SIGNATURE_RE = re.compile(r"""\$signature\s*=\s*['"](?P<sig>[^'"]+)['"]""")

# resource → 7 RESTful routes; apiResource → 5 (no create/edit).
_LARAVEL_RESOURCE_ACTIONS = {
    "resource": [
        ("get", "", "index"), ("get", "/create", "create"), ("post", "", "store"),
        ("get", "/{id}", "show"), ("get", "/{id}/edit", "edit"),
        ("put", "/{id}", "update"), ("delete", "/{id}", "destroy"),
    ],
    "apiResource": [
        ("get", "", "index"), ("post", "", "store"), ("get", "/{id}", "show"),
        ("put", "/{id}", "update"), ("delete", "/{id}", "destroy"),
    ],
}


def _php_short_name(name: str) -> str:
    return name.replace("/", "\\").split("\\")[-1]


def _laravel_handler(content: str, end: int) -> str | None:
    tail = content[end:]
    m = _LARAVEL_H_ARRAY_RE.match(tail)
    if m:
        return f"{_php_short_name(m.group('ctrl'))}@{m.group('method')}"
    m = _LARAVEL_H_STRING_RE.match(tail)
    if m:
        return f"{_php_short_name(m.group('ctrl'))}@{m.group('method')}"
    m = _LARAVEL_H_INVOKE_RE.match(tail)
    if m:
        return f"{_php_short_name(m.group('ctrl'))}@__invoke"
    return None


def _scan_laravel(content: str) -> list[ContractMatch]:
    """Laravel routes (facade + resource) + Artisan commands.

    Note: routes nested in `Route::prefix(..)->group(..)` closures are
    captured at their literal path — the group prefix is NOT auto-joined
    (closure scoping needs an AST, not regex), so no FALSE prefixes appear.
    """
    if "Route::" not in content and "Illuminate\\" not in content and "extends Command" not in content:
        return []
    hits: list[ContractMatch] = []
    for m in _LARAVEL_ROUTE_RE.finditer(content):
        method = m.group("method").lower()
        hits.append(
            ContractMatch(
                kind="http",
                framework="laravel",
                method="any" if method == "any" else method,
                path=m.group("path"),
                handler=_laravel_handler(content, m.end()),
                line=_line_of(content, m.start()),
            )
        )
    for m in _LARAVEL_RESOURCE_RE.finditer(content):
        name = m.group("path").strip("/")
        ctrl = _php_short_name(m.group("ctrl"))
        line = _line_of(content, m.start())
        for method, suffix, action in _LARAVEL_RESOURCE_ACTIONS[m.group("kind")]:
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="laravel",
                    method=method,
                    path=f"/{name}{suffix}",
                    handler=f"{ctrl}@{action}",
                    line=line,
                    confidence=0.85,
                    derivation=f"laravel_{m.group('kind')}",
                )
            )
    if "extends Command" in content:
        for m in _LARAVEL_SIGNATURE_RE.finditer(content):
            cmd = m.group("sig").split()[0] if m.group("sig") else m.group("sig")
            hits.append(
                ContractMatch(
                    kind="cli",
                    framework="artisan",
                    method="command",
                    path=cmd,
                    handler=None,
                    line=_line_of(content, m.start()),
                )
            )
    return hits


_WP_HOOK_RE = re.compile(
    rf"""\badd_(?P<typ>action|filter)\s*\(\s*{_STRING_CAPTURE}
        (?:\s*,\s*['"]?(?P<cb>[A-Za-z_][\w]*)['"]?)?
    """,
    re.VERBOSE,
)
_WP_FIRE_RE = re.compile(
    rf"""\b(?P<typ>do_action|apply_filters)\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE
)
_WP_SHORTCODE_RE = re.compile(rf"""\badd_shortcode\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE)
_WP_CPT_RE = re.compile(rf"""\bregister_post_type\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE)
_WP_REST_RE = re.compile(
    r"""\bregister_rest_route\s*\(\s*['"](?P<ns>[^'"]+)['"]\s*,\s*['"](?P<route>[^'"]+)['"]
        (?:[^)]*?['"]methods['"]\s*=>\s*['"](?P<methods>[^'"]+)['"])?
    """,
    re.VERBOSE | re.DOTALL,
)
_WP_MARKERS = (
    "add_action", "add_filter", "add_shortcode", "register_post_type",
    "register_rest_route", "do_action", "apply_filters",
)


def _scan_wordpress(content: str) -> list[ContractMatch]:
    """WordPress hooks (action/filter + fire sites), shortcodes, CPT, REST, ajax."""
    if not any(tok in content for tok in _WP_MARKERS):
        return []
    hits: list[ContractMatch] = []
    for m in _WP_HOOK_RE.finditer(content):
        hook = m.group("path")
        cb = m.group("cb")
        line = _line_of(content, m.start())
        if hook.startswith("wp_ajax_"):
            action = hook[len("wp_ajax_nopriv_"):] if hook.startswith("wp_ajax_nopriv_") else hook[len("wp_ajax_"):]
            hits.append(
                ContractMatch(
                    kind="http", framework="wp_ajax", method="post",
                    path=f"/wp-admin/admin-ajax.php?action={action}",
                    handler=cb, line=line, derivation="wp_ajax",
                )
            )
        else:
            hits.append(
                ContractMatch(
                    kind="event", framework=f"wp_{m.group('typ')}", method=m.group("typ"),
                    path=hook, handler=cb, line=line,
                )
            )
    for m in _WP_FIRE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event", framework="wp_emit", method=m.group("typ"),
                path=m.group("path"), handler=None, line=_line_of(content, m.start()),
                derivation="wp_fire",
            )
        )
    for m in _WP_SHORTCODE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event", framework="wp_shortcode", method="shortcode",
                path=m.group("path"), handler=None, line=_line_of(content, m.start()),
            )
        )
    for m in _WP_CPT_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event", framework="wp_cpt", method="post_type",
                path=m.group("path"), handler=None, line=_line_of(content, m.start()),
            )
        )
    for m in _WP_REST_RE.finditer(content):
        ns = m.group("ns").strip("/")
        route = m.group("route")
        method = (m.group("methods") or "any").split(",")[0].strip().lower()
        hits.append(
            ContractMatch(
                kind="http", framework="wp_rest", method=method,
                path=_join_paths(f"/wp-json/{ns}", route), handler=None,
                line=_line_of(content, m.start()), derivation="wp_rest",
            )
        )
    return hits


def _scan_whmcs(content: str, *, path: str) -> list[ContractMatch]:
    """WHMCS add_hook + module-function convention — implemented in TASK-069 P3."""
    return []


_MCP_NOISE_NAMES = {"name", "x", "y", "z", "foo", "bar", "tool", "test"}
_MCP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")


def _python_file_docstring(content: str) -> str | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    return ast.get_docstring(tree)


def _scan_mcp(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _MCP_TOOL_RE.finditer(content):
        name = (match.group("path") or "").strip()
        if name in _MCP_NOISE_NAMES or not _MCP_NAME_RE.match(name):
            continue
        hits.append(
            ContractMatch(
                kind="mcp",
                framework="mcp",
                method="rpc",
                path=name,
                handler=_next_def_name(content, match.end()),
                line=_line_of(content, match.start()),
            )
        )
    # Count @safe_tool decorators separately as a signal that this
    # module participates in the MCP envelope contract (Rule 14).
    if _MCP_SAFE_TOOL_RE.search(content):
        # Not a route on its own — no match emitted; callers use the
        # `@safe_tool` presence implicitly via the evidence audit.
        pass
    return hits


def _scan_celery(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _CELERY_TASK_RE.finditer(content):
        task_name = match.group("path") or match.group("handler")
        hits.append(
            ContractMatch(
                kind="event",
                framework="celery",
                method="task",
                path=task_name,
                handler=match.group("handler"),
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_channels_signals(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _CHANNELS_RECEIVER_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event",
                framework="django_signals",
                method="signal",
                path=match.group("sender"),
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_websocket(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _WEBSOCKET_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="websocket",
                framework="generic",
                method="ws",
                path=match.group("path"),
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_pubsub(content: str, *, framework_label: str) -> list[ContractMatch]:
    """R4: collect `@bus.on(...)` / `@<emitter>.subscribe(...)` matches.

    framework_label tags the source language (`python` / `ts`).
    """
    hits: list[ContractMatch] = []
    for match in _PUBSUB_ON_RE.finditer(content):
        emitter = match.group("emitter")
        event_name = match.group("path")
        # Skip noisy matches: `app.on` (Flask before_request etc.) and
        # `os.on` are clearly not pubsub. Allow when emitter has a
        # discriminating suffix (bus/emitter/events).
        emitter_tail = emitter.split(".")[-1].lower()
        if emitter_tail not in {"bus", "events", "emitter", "pubsub", "signals"}:
            continue
        hits.append(
            ContractMatch(
                kind="event",
                framework=f"{framework_label}_{emitter_tail}",
                method="on",
                path=f"{emitter}:{event_name}",
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    for match in _PUBSUB_SUBSCRIBE_RE.finditer(content):
        emitter = match.group("emitter")
        event_name = match.group("path")
        hits.append(
            ContractMatch(
                kind="event",
                framework=f"{framework_label}_subscribe",
                method="subscribe",
                path=f"{emitter}:{event_name}",
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_sse(content: str) -> list[ContractMatch]:
    """R4: FastAPI/Starlette SSE — file uses EventSourceResponse /
    ServerSentEvent. Emits one synthetic event match per file so trace
    knows the file participates in event flows."""
    hits: list[ContractMatch] = []
    m = _SSE_HINT_RE.search(content)
    if m:
        hits.append(
            ContractMatch(
                kind="event",
                framework="fastapi_sse",
                method="sse",
                path="<file_scope>",
                handler=None,
                line=_line_of(content, m.start()),
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_of(content: str, idx: int) -> int:
    return content[:idx].count("\n") + 1


def _parse_method_list(raw: str) -> list[str]:
    methods: list[str] = []
    for part in raw.split(","):
        cleaned = part.strip().strip("'\"")
        if cleaned:
            methods.append(cleaned)
    return methods


def _next_def_name(content: str, start: int) -> str | None:
    """Find the next `def name(` after `start` — the decorated handler."""
    match = re.search(r"\s*def\s+([A-Za-z_][\w]*)", content[start:])
    return match.group(1) if match else None


def _join_paths(a: str, b: str) -> str:
    a = a.rstrip("/")
    b = b.strip()
    if not b.startswith("/"):
        b = "/" + b
    return f"{a}{b}"


def _go_group_prefixes(content: str) -> dict[str, str]:
    """Map a Go group variable → its full route prefix.

    Resolves nesting when the parent group is declared first
    (`v1 := app.Group("/api"); v2 := v1.Group("/v2")` → v2 = /api/v2).
    """
    prefixes: dict[str, str] = {}
    for m in _GO_GROUP_ASSIGN_RE.finditer(content):
        var = m.group("var")
        parent = m.group("app")
        seg = m.group("path")
        base = prefixes.get(parent, "")
        prefixes[var] = _join_paths(base, seg) if base else seg
    return prefixes


def _go_route_handler(content: str, end_idx: int) -> str | None:
    """Return the handler identifier passed after a route's path string."""
    m = _GO_ROUTE_HANDLER_RE.match(content[end_idx:])
    return m.group("handler") if m else None


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
            "route.ts", "route.tsx", "route.js", "route.jsx",
            "page.ts", "page.tsx", "page.js", "page.jsx",
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


__all__ = ["EXTRACTOR_ID", "ContractMatch", "extract"]
