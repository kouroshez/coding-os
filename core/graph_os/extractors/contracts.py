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
    kind: str  # "http" | "mcp" | "grpc" | "event" | "websocket"
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

# NestJS: @Controller('/x'), @Get('/y')
_NEST_METHOD_RE = re.compile(
    rf"""@(?P<method>Get|Post|Put|Patch|Delete)\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
_NEST_CONTROLLER_RE = re.compile(
    rf"""@Controller\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE
)

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
    rf"""@(?:receiver)\s*\(\s*[A-Za-z_][\w]*\s*,\s*sender\s*=\s*(?P<sender>[A-Za-z_][\w.]*)""",
    re.VERBOSE,
)
_WEBSOCKET_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.sock\.route\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# Dynamic hints — fetch with template literal.
_DYNAMIC_FETCH_RE = re.compile(r"fetch\s*\(\s*`[^`]*\$\{")


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
        elif normalised.endswith(".ts") or normalised.endswith(".tsx"):
            matches.extend(_scan_nextjs(content, path=normalised))
            matches.extend(_scan_nest(content))
        elif normalised.endswith(".go"):
            matches.extend(_scan_fiber(content))
    except Exception as exc:  # noqa: BLE001
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


def _scan_nextjs(content: str, *, path: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    # Path becomes the URL — normalise [id] → {id}, [...slug] → *slug.
    url = _nextjs_route_path(path)
    for match in _NEXTJS_ROUTE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="http",
                framework="nextjs",
                method=match.group("method").lower(),
                path=url,
                handler=None,
                line=_line_of(content, match.start()),
                note="dynamic_segment" if _has_dynamic_segment(path) else None,
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


def _scan_fiber(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    groups: list[str] = []
    for match in _FIBER_GROUP_RE.finditer(content):
        groups.append(match.group("path"))
    for match in _FIBER_ROUTE_RE.finditer(content):
        path = match.group("path")
        if groups:
            path = _join_paths(groups[-1], path)
        hits.append(
            ContractMatch(
                kind="http",
                framework="fiber",
                method=match.group("method").lower(),
                path=path,
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


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


def _nextjs_route_path(file_path: str) -> str:
    """Turn an `app/users/[id]/route.ts` path into `/users/{id}`."""
    normalised = _normalize_path(file_path)
    parts = normalised.split("/")
    try:
        idx = parts.index("app")
    except ValueError:
        try:
            idx = parts.index("pages")
        except ValueError:
            return normalised
    segments = parts[idx + 1 :]
    if segments and segments[-1] in ("route.ts", "route.tsx", "page.ts", "page.tsx"):
        segments = segments[:-1]
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
