"""graph_os — Go Fiber routes from the syntax tree.

A route is `<router>.<Verb>(path, handlers...)` on a value known to be a Fiber
router: a parameter typed `*fiber.App`, `fiber.Router` or `*fiber.Group`, a local
bound to `fiber.New(...)` or `<router>.Group(prefix, ...)`, the router a
`Route(prefix, func(r fiber.Router) {...})` callback receives, or an app another
router `Mount`s. Knowing the receiver is what keeps `resp.Header.Get("Content-Type")`
from reading as a route. Fiber runs a route's handlers in order, so the last
argument is the handler and the ones before it are middleware.

A router a function receives gets its prefix from the call sites in the same
file that pass one in (`h.registerReports(api)`). A prefix only another file
knows leaves the route relative and provisional (`@<file>`, `prefix:
unresolved`); a call passing a router to another file is a `passes_router` edge
the link pass uses to compose it. Route nodes and edges are built in
_go_route_emit.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from typing import Any

from ..types import EvidenceSignal, GraphEdge
from ._go_calls import (
    GoCallTarget,
    GoScope,
    _bound_names,
    _call_target,
    _collect_local_callables,
    _parse_receiver_var_type,
)
from ._go_route_emit import (
    ROUTE_CONFIDENCE,
    _arguments,
    _Callers,
    _emit,
    _Function,
    _join,
    _Prefix,
    _Route,
    _Router,
)
from ._go_uids import EXTRACTOR_ID, _find_field, _node_text, func_uid, method_uid
from .md_links import ExtractionResult

FIBER_IMPORT = "github.com/gofiber/fiber"
MAX_ROUTER_DEPTH = 16
MAX_CALL_DEPTH = 4

_VERBS = frozenset(
    {"Get", "Post", "Put", "Patch", "Delete", "Head", "Options", "Connect", "Trace", "All"}
)
_ROUTER_TYPES = frozenset({"App", "Router", "Group"})
_MOUNTS = frozenset({"Mount", "Use"})
_STRINGS = frozenset({"interpreted_string_literal", "raw_string_literal"})
_DECLARATIONS = frozenset({"function_declaration", "method_declaration"})


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
            for prefix in _sorted(_prefixes(function, route.router, callers, 0)):
                _emit(route, function, prefix, path, file_uid_str, seen, result)
    _emit_router_passes(functions, callers, result)


def _sorted(prefixes: list[_Prefix]) -> list[_Prefix]:
    return sorted(set(prefixes), key=lambda item: (item[0], item[1], item[2] or ("", -1)))


def _emit_router_passes(
    functions: list[_Function], callers: _Callers, result: ExtractionResult
) -> None:
    # A router handed to a function in another file: the link pass composes the
    # callee's routes from the prefix recorded here (per argument position).
    notes: dict[tuple[str, str], list[EvidenceSignal]] = defaultdict(list)
    for function in functions:
        for callee, index, router in function.remote_passes:
            for prefix, known, origin in _sorted(_prefixes(function, router, callers, 0)):
                # A known prefix travels whole; only an unknown one waits on a caller.
                origin = None if known else origin
                source = origin[0] if origin else function.scope.uid
                if source is None or (not known and origin is None):
                    continue
                note = {"index": index, "prefix": prefix, "param": origin[1] if origin else None}
                notes[(source, callee)].append(
                    EvidenceSignal("fiber_router_pass", ROUTE_CONFIDENCE, note=json.dumps(note))
                )
    for (source, callee), evidence in sorted(notes.items()):
        result.edges.append(
            GraphEdge(
                source_uid=source,
                target_uid=callee,
                edge_type="passes_router",
                extractor=EXTRACTOR_ID,
                confidence=ROUTE_CONFIDENCE,
                evidence=tuple(evidence),
            )
        )


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
                    known=router_type == "App", parameter=index, app=router_type == "App"
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
        current = function.routers.get(mounted)
        if arguments[1].type != "identifier" or current is None:
            return
        if current.parent is None and current.parameter is None:
            function.routers[mounted] = _Router(parent=receiver, segment=path)
        else:
            function.routers[mounted] = replace(current, mounts=(*current.mounts, (receiver, path)))


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
    if target is None:
        return
    same_file = target.uid.startswith((f"code:function:{path}::", f"code:method:{path}::"))
    passes = function.passes if same_file else function.remote_passes
    passes.extend((target.uid, index, router) for index, router in routers)


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


def _mount_chains(
    function: _Function, router: str, depth: int
) -> list[tuple[list[str], bool, _Router | None]]:
    # Every way `router` hangs off its root: (segments root→router, known, root).
    current = function.routers.get(router)
    if current is None:
        return [([], True, None)]
    chains: list[tuple[list[str], bool, _Router | None]] = []
    for parent, segment in [(current.parent, current.segment), *current.mounts]:
        if parent is None or depth + 1 >= MAX_ROUTER_DEPTH:
            chains.append(([segment], current.known, current))
            continue
        for segments, known, root in _mount_chains(function, parent, depth + 1):
            chains.append(([*segments, segment], known and current.known, root))
    return chains


def _prefixes(function: _Function, router: str, callers: _Callers, depth: int) -> list[_Prefix]:
    found: list[_Prefix] = []
    for segments, known, root in _mount_chains(function, router, 0):
        suffix = _join(*segments)
        parameter = root.parameter if root is not None else None
        passed = (
            callers.get((function.scope.uid or "", parameter), [])
            if parameter is not None and depth < MAX_CALL_DEPTH
            else []
        )
        if not passed:
            waits = not known or (root is not None and root.app)
            origin = (
                (function.scope.uid, parameter)
                if waits and parameter is not None and function.scope.uid
                else None
            )
            found.append((suffix, known, origin))
            continue
        found += [
            (_join(prefix, suffix), caller_known, origin)
            for caller, argument in passed
            for prefix, caller_known, origin in _prefixes(caller, argument, callers, depth + 1)
        ]
    return found
