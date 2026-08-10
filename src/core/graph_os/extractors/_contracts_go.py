"""Go contract scanners — Fiber, Gin, Echo, Chi, gorilla/mux, net/http, gRPC, CLIs."""

from __future__ import annotations

import re

from ._contracts_shared import _STRING_CAPTURE, ContractMatch, _join_paths, _line_of

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
