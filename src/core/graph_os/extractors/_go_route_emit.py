"""graph_os — Go Fiber routes: the route model and the nodes and edges one route becomes.

Leaf of the route walker (_go_routes): a route node keyed by method and full
path (provisional `@<file>` while its router's prefix waits on another file),
its `handles_route` and `contains` edges from the file, and `calls` edges to its
handler and, at lower confidence, its middleware.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._go_calls import GoCallTarget, GoScope
from ._go_uids import EXTRACTOR_ID, _find_field, _node_text
from .md_links import ExtractionResult

ROUTE_CONFIDENCE = 0.9
MIDDLEWARE_CONFIDENCE = 0.6

_Resolver = Callable[[Any], GoCallTarget | None]


@dataclass(frozen=True)
class _Router:
    parent: str | None = None
    segment: str = ""
    known: bool = True
    parameter: int | None = None


@dataclass(frozen=True)
class _Route:
    router: str
    verb: str
    path: str
    call: Any


@dataclass
class _Function:
    scope: GoScope
    content: bytes
    aliases: set[str]
    resolve: _Resolver
    routers: dict[str, _Router] = field(default_factory=dict)
    routes: list[_Route] = field(default_factory=list)
    passes: list[tuple[str, int, str]] = field(default_factory=list)
    remote_passes: list[tuple[str, int, str]] = field(default_factory=list)


_Callers = dict[tuple[str, int], list[tuple[_Function, str]]]
# The function and parameter a prefix stops at when only another file knows it.
_Origin = tuple[str, int] | None
_Prefix = tuple[str, bool, _Origin]


def _arguments(call: Any) -> list[Any]:
    arguments = _find_field(call, "arguments")
    if arguments is None:
        return []
    return [argument for argument in arguments.named_children if argument.type != "comment"]


def _join(*parts: str) -> str:
    joined = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return f"/{joined}"


def _emit(
    route: _Route,
    function: _Function,
    prefix: _Prefix,
    path: str,
    file_uid_str: str,
    seen: set[str],
    result: ExtractionResult,
) -> None:
    known, origin = prefix[1], prefix[2]
    full_path = _join(prefix[0], route.path)
    method = route.verb.upper()
    # Relative to a router another file passes in: provisional until the link
    # pass composes it, and per file so two packages' `/` never merge.
    uid = f"cos:route:{method}:{full_path}" + (f"@{path}" if origin else "")
    if uid in seen:
        return
    seen.add(uid)
    arguments = _arguments(route.call)[1:]
    handler, middleware = (arguments[-1], arguments[:-1]) if arguments else (None, [])
    line = route.call.start_point[0] + 1
    span = f"{path}:{line}"
    metadata: dict[str, Any] = {
        "kind": "http",
        "framework": "fiber",
        "method": route.verb.lower(),
        "path": full_path,
        "handler": _describe(handler, function) if handler is not None else None,
        "middleware": [_describe(argument, function) for argument in middleware],
        "extractor": EXTRACTOR_ID,
    }
    if not known:
        metadata["prefix"] = "unresolved"
    if origin:
        metadata.update(route_path=full_path, router_owner=origin[0], router_param=origin[1])
    result.nodes.append(
        GraphNode(
            uid=uid,
            kind="cos:route",
            label=f"{method} {full_path}",
            file_path=path,
            start_line=line,
            lang="go",
            metadata=metadata,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=file_uid_str,
            target_uid=uid,
            edge_type="handles_route",
            extractor=EXTRACTOR_ID,
            confidence=ROUTE_CONFIDENCE,
            source_span=span,
            evidence=(EvidenceSignal("fiber_http", ROUTE_CONFIDENCE),),
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=file_uid_str,
            target_uid=uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )
    if handler is not None:
        target = _handler_target(handler, function)
        if target is not None:
            _call_edge(uid, target, ROUTE_CONFIDENCE, span, result)
    for argument in middleware:
        target = _handler_target(argument, function)
        if target is not None and target.signal != "fiber_inline_handler":
            _call_edge(uid, target, MIDDLEWARE_CONFIDENCE, span, result)


def _handler_target(expression: Any, function: _Function) -> GoCallTarget | None:
    if expression.type == "func_literal":
        # The code that answers lives inline, in the function registering it.
        uid = function.scope.uid
        return GoCallTarget(uid, 1.0, "fiber_inline_handler") if uid else None
    if expression.type == "call_expression":
        expression = _find_field(expression, "function")
    return function.resolve(expression) if expression is not None else None


def _call_edge(
    route_uid: str, target: GoCallTarget, weight: float, span: str, result: ExtractionResult
) -> None:
    confidence = round(weight * target.confidence, 3)
    result.edges.append(
        GraphEdge(
            source_uid=route_uid,
            target_uid=target.uid,
            edge_type="calls",
            extractor=EXTRACTOR_ID,
            confidence=confidence,
            source_span=span,
            evidence=(EvidenceSignal(target.signal, confidence),),
        )
    )


def _describe(expression: Any, function: _Function) -> str:
    if expression.type == "func_literal":
        return "func"
    if expression.type == "call_expression":
        callee = _find_field(expression, "function")
        return f"{_node_text(callee, function.content)}(...)" if callee is not None else "call"
    return _node_text(expression, function.content)
