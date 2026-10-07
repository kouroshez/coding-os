"""FastAPI routes and router mounts from the Python syntax tree.

A route is a `@<router>.get|post|put|patch|delete|head|options|trace(path)`,
`@<router>.api_route(path, methods=[...])` or `@<router>.websocket(path)`
decorator, or a `<router>.add_api_route(path, endpoint, methods=[...])` call; the
path is the first argument or `path=`, and "" — a router's own root — counts. A
router built in the same file lends its `APIRouter(prefix=...)`, and a
`include_router(child, prefix=...)` there composes. Routers and mounts are also
recorded on the file, because the prefix that completes a path usually sits in
another file — a shared `router` module, or the app that includes it — and the
linker composes them (`link_fastapi_routes`). Reading the tree, not the text,
keeps example code in docstrings out.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from ._contracts_shared import ContractMatch

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
_ROUTER_FACTORIES = frozenset({"APIRouter", "FastAPI"})
_ADD_ROUTE = frozenset({"add_api_route", "add_api_websocket_route"})
MAX_MOUNT_DEPTH = 8
# `{uid:path}` routes the same URL a client calls as `{uid}` (OpenAPI's form).
_CONVERTER_RE = re.compile(r"\{(\w+):[^}]+\}")
# A routes module that only imports a shared `router` never names fastapi.
_ROUTE_DECORATOR_RE = re.compile(
    r"@\w+\.(?:get|post|put|patch|delete|head|options|trace|api_route|websocket)\("
)

# (router, method, path, handler, line, (kind, reference)): kind is function,
# method or import; an import reference is `module:name`, dots still relative.
_Site = tuple[str, str, str, str | None, int, tuple[str, str] | None]


@dataclass
class FastApiScan:
    routes: list[ContractMatch] = field(default_factory=list)
    routers: dict[str, str] = field(default_factory=dict)
    apps: set[str] = field(default_factory=set)
    mounts: list[list[Any]] = field(default_factory=list)


def scan_fastapi(content: str) -> FastApiScan:
    scan = FastApiScan()
    decorated = _ROUTE_DECORATOR_RE.search(content) and "flask" not in content
    if "fastapi" not in content and "APIRouter" not in content and not decorated:
        return scan
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return scan
    prefixes = scan.routers = _router_prefixes(tree, scan.apps)
    parents: dict[str, tuple[str, str]] = {}
    for call in _calls(tree, "include_router"):
        parent = _receiver(call)
        child = ast.unparse(call.args[0]) if call.args else ""
        prefix = _string(_keyword(call, "prefix")) or ""
        if not parent or not child:
            continue
        scan.mounts.append([parent, child, prefix, call.lineno])
        if child in prefixes and child != parent:
            parents.setdefault(child, (parent, prefix))
    for router, method, path, handler, line, reference in _route_sites(tree):
        path = _CONVERTER_RE.sub(r"{\1}", path)
        full = _join(_mount_prefix(router, parents, prefixes), prefixes.get(router, ""), path)
        extra: tuple[tuple[str, Any], ...] = (
            ("router", router),
            ("route_path", path),
            ("syntax_tree", True),
            ("handler_reference", reference),
        )
        if _root(router, parents) not in scan.apps:
            # Another file may still prefix it; a file-scoped uid keeps two
            # routers' `/items` apart until the linker composes the real path.
            extra += (("provisional", True),)
        scan.routes.append(
            ContractMatch(
                kind="websocket" if method == "ws" else "http",
                framework="fastapi",
                method=method,
                path=full,
                handler=handler,
                line=line,
                extra=extra,
            )
        )
    return scan


def _router_prefixes(tree: ast.Module, apps: set[str]) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        factory = ast.unparse(node.value.func).rsplit(".", 1)[-1]
        if factory not in _ROUTER_FACTORIES:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefix = _CONVERTER_RE.sub(r"{\1}", _string(_keyword(node.value, "prefix")) or "")
                prefixes.setdefault(target.id, prefix)
                if factory == "FastAPI":
                    apps.add(target.id)
    return prefixes


def _root(router: str, parents: dict[str, tuple[str, str]]) -> str:
    current = router
    for _ in range(MAX_MOUNT_DEPTH):
        if current not in parents:
            break
        current = parents[current][0]
    return current


def _mount_prefix(
    router: str, parents: dict[str, tuple[str, str]], prefixes: dict[str, str]
) -> str:
    segments: list[str] = []
    current = router
    for _ in range(MAX_MOUNT_DEPTH):
        if current not in parents:
            break
        parent, prefix = parents[current]
        segments.append(prefixes.get(parent, "") + prefix)
        current = parent
    return "".join(reversed(segments))


def _route_sites(tree: ast.Module) -> list[_Site]:
    # A handler is named as code_python names it: `create_app.ping` inside a
    # factory, the method `Items.list_items` on a class.
    sites: list[_Site] = []
    imported = _imported_names(tree)
    stack: list[tuple[ast.AST, tuple[str, ...], bool]] = [(tree, (), False)]
    while stack:
        node, scope, in_class = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = ".".join((*scope, child.name))
                kind = "method" if in_class else "function"
                for decorator in child.decorator_list:
                    sites += _decorator_routes(decorator, qualname, kind)
                stack.append((child, (*scope, child.name), False))
            elif isinstance(child, ast.ClassDef):
                stack.append((child, (*scope, child.name), True))
            else:
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr in _ADD_ROUTE
                ):
                    sites += _added_routes(child, child.func.attr, imported)
                stack.append((child, scope, in_class))
    return sites


def _imported_names(tree: ast.Module) -> dict[str, str]:
    # Local name → the module it comes from, relative dots kept for the caller.
    imported: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                imported[alias.asname or alias.name] = f"{module}:{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported[alias.asname or alias.name.split(".")[0]] = alias.name
    return imported


def _decorator_routes(decorator: ast.expr, handler: str, kind: str) -> list[_Site]:
    if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
        return []
    router, verb, path = _receiver(decorator), decorator.func.attr, _path(decorator)
    if not router or path is None:
        return []
    if verb in HTTP_METHODS:
        methods = [verb]
    elif verb == "api_route":
        methods = _methods(decorator) or ["get"]
    elif verb == "websocket":
        methods = ["ws"]
    else:
        return []
    return [
        (router, method, path, handler, decorator.lineno, (kind, handler)) for method in methods
    ]


def _added_routes(call: ast.Call, attribute: str, imported: dict[str, str]) -> list[_Site]:
    router, path = _receiver(call), _path(call)
    if not router or path is None:
        return []
    endpoint = call.args[1] if len(call.args) > 1 else _keyword(call, "endpoint")
    handler = ast.unparse(endpoint) if endpoint is not None else None
    reference = _endpoint_reference(endpoint, imported)
    if attribute == "add_api_websocket_route":
        return [(router, "ws", path, handler, call.lineno, reference)]
    return [
        (router, method, path, handler, call.lineno, reference)
        for method in _methods(call) or ["get"]
    ]


def _endpoint_reference(
    endpoint: ast.expr | None, imported: dict[str, str]
) -> tuple[str, str] | None:
    # `add_api_route('/x', health)` with `health` imported names the function
    # in its own module, not a phantom in this one.
    if isinstance(endpoint, ast.Name):
        source = imported.get(endpoint.id)
        if source is None:
            return ("function", endpoint.id)
        if ":" in source:
            return ("import", source)
        return None
    if isinstance(endpoint, ast.Attribute) and isinstance(endpoint.value, ast.Name):
        source = imported.get(endpoint.value.id)
        if source is not None:
            module = source.replace(":", ".")
            return ("import", f"{module}:{endpoint.attr}")
    return None


def _calls(tree: ast.Module, attribute: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


def _receiver(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    return ""


def _path(call: ast.Call) -> str | None:
    return _string(call.args[0] if call.args else _keyword(call, "path"))


def _methods(call: ast.Call) -> list[str]:
    value = _keyword(call, "methods")
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return []
    return [method.lower() for method in (_string(item) for item in value.elts) if method]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _string(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _join(*parts: str) -> str:
    # FastAPI concatenates (a prefix may not end in "/"), so a trailing slash
    # the decorator wrote is part of the route.
    joined = "".join(parts)
    return joined if joined.startswith("/") else f"/{joined}"
