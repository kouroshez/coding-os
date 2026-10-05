"""graph_os — Go Fiber routes from the syntax tree.

A route is `<router>.<Verb>(path, handlers...)` on a value known to be a Fiber
router: a parameter typed `*fiber.App`, `fiber.Router` or `*fiber.Group`, a local
bound to `fiber.New(...)` or `<router>.Group(prefix, ...)`, the router a
`Route(prefix, func(r fiber.Router) {...})` callback receives, or an app another
router `Mount`s. Knowing the receiver is what keeps `resp.Header.Get("Content-Type")`
from reading as a route. Fiber runs a route's handlers in order, so the last
argument is the handler and the ones before it are middleware.

A router a function receives gets its prefix from the call sites in the same
file that pass one in (`h.registerReports(api)`); a prefix that only another
file knows leaves the route relative, marked `prefix: unresolved`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._go_calls import (
    GoCallTarget,
    GoScope,
    _bound_names,
    _call_target,
    _collect_local_callables,
    _parse_receiver_var_type,
)
from ._go_uids import EXTRACTOR_ID, _find_field, _node_text, func_uid, method_uid
from .md_links import ExtractionResult

FIBER_IMPORT = "github.com/gofiber/fiber"
ROUTE_CONFIDENCE = 0.9
MIDDLEWARE_CONFIDENCE = 0.6
MAX_ROUTER_DEPTH = 16
MAX_CALL_DEPTH = 4

_VERBS = frozenset(
    {"Get", "Post", "Put", "Patch", "Delete", "Head", "Options", "Connect", "Trace", "All"}
)
_ROUTER_TYPES = frozenset({"App", "Router", "Group"})
_MOUNTS = frozenset({"Mount", "Use"})
_STRINGS = frozenset({"interpreted_string_literal", "raw_string_literal"})
_DECLARATIONS = frozenset({"function_declaration", "method_declaration"})

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


_Callers = dict[tuple[str, int], list[tuple[_Function, str]]]


def walk_fiber_routes(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    directory: str,
    file_uid_str: str,
    imports: dict[str, tuple[str, str | None]],
    result: ExtractionResult,
) -> None:
    aliases = {alias for alias, (target, _) in imports.items() if target.startswith(FIBER_IMPORT)}
    if not aliases:
        return
    local_funcs, local_methods = _collect_local_callables(root, content_bytes, path)
    functions: list[_Function] = []
    for declaration in _declarations(root):
        scope = _scope(declaration, content_bytes, path)
        bound = _bound_names(declaration, content_bytes)

        def resolve(
            expression: Any, scope: GoScope = scope, bound: set[str] = bound
        ) -> GoCallTarget | None:
            return _call_target(
                expression,
                scope,
                bound,
                content_bytes,
                directory,
                imports,
                local_funcs,
                local_methods,
            )

        function = _Function(scope, content_bytes, aliases, resolve)
        _parameters(declaration, function)
        _collect(declaration, function, path)
        functions.append(function)
    callers: _Callers = defaultdict(list)
    for function in functions:
        for callee, index, router in function.passes:
            callers[(callee, index)].append((function, router))
    seen: set[str] = set()
    for function in functions:
        for route in function.routes:
            for prefix, known in sorted(set(_prefixes(function, route.router, callers, 0))):
                _emit(route, function, prefix, known, path, file_uid_str, seen, result)


def _declarations(root: Any) -> list[Any]:
    return [child for child in root.children if child.type in _DECLARATIONS]


def _scope(declaration: Any, content: bytes, path: str) -> GoScope:
    name_node = _find_field(declaration, "name")
    name = _node_text(name_node, content) if name_node is not None else ""
    if declaration.type == "function_declaration":
        return GoScope(func_uid(path, name) if name else None, "", "", declaration)
    receiver_var, receiver_type = _parse_receiver_var_type(
        _find_field(declaration, "receiver"), content
    )
    uid = method_uid(path, receiver_type, name) if name and receiver_type else None
    return GoScope(uid, receiver_var, receiver_type, declaration)


def _parameters(declaration: Any, function: _Function) -> None:
    parameters = _find_field(declaration, "parameters")
    index = 0
    for parameter in parameters.named_children if parameters is not None else []:
        router_type = _router_type(_find_field(parameter, "type"), function)
        for name in parameter.children_by_field_name("name"):
            if router_type:
                # The app is the root; a Router or Group arrives with a prefix
                # only its callers know.
                function.routers[_node_text(name, function.content)] = _Router(
                    known=router_type == "App", parameter=index
                )
            index += 1


def _collect(declaration: Any, function: _Function, path: str) -> None:
    stack = [declaration]
    while stack:
        node = stack.pop()
        if node.type == "parameter_declaration" and _router_type(
            _find_field(node, "type"), function
        ):
            for name in node.children_by_field_name("name"):
                function.routers.setdefault(
                    _node_text(name, function.content), _Router(known=False)
                )
        elif node.type in ("short_var_declaration", "assignment_statement"):
            _bind(_find_field(node, "left"), _find_field(node, "right"), function)
        elif node.type == "var_spec":
            values = _find_field(node, "value")
            for name, value in zip(
                node.children_by_field_name("name"),
                values.named_children if values is not None else [],
                strict=False,
            ):
                _bind_one(_node_text(name, function.content), value, function)
        elif node.type == "call_expression":
            _register(node, function)
            _record_pass(node, function, path)
        stack.extend(reversed(node.children))


def _router_type(type_node: Any, function: _Function) -> str | None:
    while type_node is not None and type_node.type == "pointer_type":
        type_node = next(iter(type_node.named_children), None)
    if type_node is None or type_node.type != "qualified_type":
        return None
    package, name = _find_field(type_node, "package"), _find_field(type_node, "name")
    if (
        package is None
        or name is None
        or _node_text(package, function.content) not in function.aliases
    ):
        return None
    type_name = _node_text(name, function.content)
    return type_name if type_name in _ROUTER_TYPES else None


def _bind(left: Any, right: Any, function: _Function) -> None:
    if left is None or right is None:
        return
    for name, value in zip(left.named_children, right.named_children, strict=False):
        if name.type == "identifier":
            _bind_one(_node_text(name, function.content), value, function)


def _bind_one(name: str, value: Any, function: _Function) -> None:
    if value.type == "identifier" and _node_text(value, function.content) in function.routers:
        function.routers[name] = _Router(parent=_node_text(value, function.content))
        return
    receiver, member, arguments = _selector_call(value, function)
    if receiver in function.aliases and member == "New":
        function.routers[name] = _Router()
    elif receiver in function.routers and member == "Group":
        prefix = _string_argument(arguments, 0, function)
        function.routers[name] = _Router(
            parent=receiver, segment=prefix or "", known=prefix is not None
        )


def _register(call: Any, function: _Function) -> None:
    receiver, member, arguments = _selector_call(call, function)
    path = _string_argument(arguments, 0, function)
    if receiver and receiver not in function.routers:
        # An app built by a constructor elsewhere has no type here; a verb on
        # it with a `/`-rooted literal is still a route, its prefix unknown.
        if member not in _VERBS or path is None or not path.startswith("/"):
            return
        function.routers[receiver] = _Router(known=False)
    if member in _VERBS and path is not None:
        function.routes.append(_Route(receiver, member, path, call))
    elif member == "Route" and path is not None:
        callback = next((a for a in arguments if a.type == "func_literal"), None)
        parameter = _first_parameter(callback, function)
        if parameter:
            function.routers[parameter] = _Router(parent=receiver, segment=path)
    elif member in _MOUNTS and path is not None and len(arguments) > 1:
        mounted = _node_text(arguments[1], function.content)
        if arguments[1].type == "identifier" and mounted in function.routers:
            function.routers[mounted] = _Router(parent=receiver, segment=path)


def _record_pass(call: Any, function: _Function, path: str) -> None:
    arguments = _arguments(call)
    routers = [
        (index, _node_text(argument, function.content))
        for index, argument in enumerate(arguments)
        if argument.type == "identifier"
        and _node_text(argument, function.content) in function.routers
    ]
    callee = _find_field(call, "function")
    target = function.resolve(callee) if routers and callee is not None else None
    if target is None or not target.uid.startswith(
        (f"code:function:{path}::", f"code:method:{path}::")
    ):
        return
    function.passes.extend((target.uid, index, router) for index, router in routers)


def _selector_call(node: Any, function: _Function) -> tuple[str, str, list[Any]]:
    if node is None or node.type != "call_expression":
        return "", "", []
    callee = _find_field(node, "function")
    if callee is None or callee.type != "selector_expression":
        return "", "", []
    operand, member = _find_field(callee, "operand"), _find_field(callee, "field")
    if operand is None or member is None or operand.type != "identifier":
        return "", "", []
    return (
        _node_text(operand, function.content),
        _node_text(member, function.content),
        _arguments(node),
    )


def _arguments(call: Any) -> list[Any]:
    arguments = _find_field(call, "arguments")
    if arguments is None:
        return []
    return [argument for argument in arguments.named_children if argument.type != "comment"]


def _string_argument(arguments: list[Any], index: int, function: _Function) -> str | None:
    if len(arguments) <= index or arguments[index].type not in _STRINGS:
        return None
    return _node_text(arguments[index], function.content)[1:-1]


def _first_parameter(callback: Any, function: _Function) -> str | None:
    parameters = _find_field(callback, "parameters") if callback is not None else None
    for declaration in parameters.named_children if parameters is not None else []:
        names = declaration.children_by_field_name("name")
        if names:
            return _node_text(names[0], function.content)
    return None


def _prefixes(
    function: _Function, router: str, callers: _Callers, depth: int
) -> list[tuple[str, bool]]:
    segments: list[str] = []
    known = True
    root: _Router | None = None
    current: str | None = router
    for _ in range(MAX_ROUTER_DEPTH):
        root = function.routers.get(current or "")
        if root is None:
            break
        segments.append(root.segment)
        known = known and root.known
        current = root.parent
        if current is None:
            break
    suffix = _join(*reversed(segments))
    passed = (
        callers.get((function.scope.uid or "", root.parameter), [])
        if root is not None and root.parameter is not None and depth < MAX_CALL_DEPTH
        else []
    )
    if not passed:
        return [(suffix, known)]
    return [
        (_join(prefix, suffix), caller_known)
        for caller, argument in passed
        for prefix, caller_known in _prefixes(caller, argument, callers, depth + 1)
    ]


def _join(*parts: str) -> str:
    joined = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return f"/{joined}"


def _emit(
    route: _Route,
    function: _Function,
    prefix: str,
    known: bool,
    path: str,
    file_uid_str: str,
    seen: set[str],
    result: ExtractionResult,
) -> None:
    full_path = _join(prefix, route.path)
    method = route.verb.upper()
    uid = f"cos:route:{method}:{full_path}"
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
