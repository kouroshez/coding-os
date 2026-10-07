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
    constants = _string_constants(tree)
    unknown: set[str] = set()
    prefixes = scan.routers = _router_prefixes(tree, scan.apps, constants, unknown)
    # Every mount a router has: included twice, it serves both paths.
    parents: dict[str, list[tuple[str, str, bool]]] = {}
    mounts = [(call, "include_router") for call in _calls(tree, "include_router")]
    mounts += [(call, "mount") for call in _calls(tree, "mount")]
    for call, kind in sorted(mounts, key=lambda item: item[0].lineno):
        parent = _receiver(call)
        if kind == "mount":
            # `app.mount("/sub", sub_app)`; a `StaticFiles(...)` is no router.
            child_node = call.args[1] if len(call.args) > 1 else _keyword(call, "app")
            prefix_node = call.args[0] if call.args else _keyword(call, "path")
            if not isinstance(child_node, ast.Name):
                continue
        else:
            child_node = call.args[0] if call.args else None
            prefix_node = _keyword(call, "prefix")
        child = ast.unparse(child_node) if child_node is not None else ""
        prefix = _prefix_value(prefix_node, constants) if prefix_node is not None else ""
        if not parent or not child:
            continue
        scan.mounts.append([parent, child, prefix or "", call.lineno])
        if child in prefixes and child != parent:
            parents.setdefault(child, []).append((parent, prefix or "", prefix is not None))
    for router, method, path, handler, line, reference in _route_sites(tree):
        path = _CONVERTER_RE.sub(r"{\1}", path)
        for mount_prefix, known, root in _mount_chains(router, parents, prefixes, unknown):
            full = _join(mount_prefix, prefixes.get(router, ""), path)
            extra: tuple[tuple[str, Any], ...] = (
                ("router", router),
                ("route_path", path),
                ("syntax_tree", True),
                ("handler_reference", reference),
            )
            if not known:
                # A prefix only run time knows (`settings.API_PREFIX`): say so.
                extra += (("prefix", "unresolved"),)
            if root not in scan.apps:
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


def _router_prefixes(
    tree: ast.Module, apps: set[str], constants: dict[str, str], unknown: set[str]
) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(
            node.value, ast.Call
        ):
            continue
        factory = ast.unparse(node.value.func).rsplit(".", 1)[-1]
        if factory not in _ROUTER_FACTORIES:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        keyword = _keyword(node.value, "prefix")
        prefix = _prefix_value(keyword, constants) if keyword is not None else ""
        for target in targets:
            if isinstance(target, ast.Name):
                prefixes.setdefault(target.id, _CONVERTER_RE.sub(r"{\1}", prefix or ""))
                if prefix is None:
                    unknown.add(target.id)
                if factory == "FastAPI":
                    apps.add(target.id)
    return prefixes


def _string_constants(tree: ast.Module) -> dict[str, str]:
    # `PREFIX = "/api"` at module level is as good as the literal.
    constants: dict[str, str] = {}
    for node in tree.body:
        value = _string(node.value) if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        for target in targets if value is not None else ():
            if isinstance(target, ast.Name):
                constants[target.id] = str(value)
    return constants


def _prefix_value(node: ast.expr, constants: dict[str, str]) -> str | None:
    literal = _string(node)
    if literal is not None:
        return literal
    return constants.get(node.id) if isinstance(node, ast.Name) else None


def _mount_chains(
    router: str,
    parents: dict[str, list[tuple[str, str, bool]]],
    prefixes: dict[str, str],
    unknown: set[str],
    depth: int = 0,
) -> list[tuple[str, bool, str]]:
    # (prefix above the router, every prefix known, the root it hangs from) per mount path.
    known = router not in unknown
    if router not in parents or depth >= MAX_MOUNT_DEPTH:
        return [("", known, router)]
    chains = []
    for parent, prefix, prefix_known in parents[router]:
        for above, above_known, root in _mount_chains(
            parent, parents, prefixes, unknown, depth + 1
        ):
            chains.append(
                (
                    above + prefixes.get(parent, "") + prefix,
                    known and prefix_known and above_known,
                    root,
                )
            )
    return chains


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
