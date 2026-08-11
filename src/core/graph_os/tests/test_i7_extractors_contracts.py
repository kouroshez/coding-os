"""I.7 tests — shell + yaml + contracts extractors.

Ship gate (Section 19 I.7):
  - full coding-os hook graph visible
  - cos-env.sh inbound edges ≥ 30
  - contracts detector finds all 21 MCP tools
  - external fixture: DRF / FastAPI / Next.js dynamic routes
"""

from __future__ import annotations

import textwrap

from graph_os.extractors import contracts


def _go_ts_available() -> bool:
    """True when tree-sitter-go grammar is importable — the AST-driven Go
    extractor (embedded fields, generics, const/var metadata) needs it.
    """
    try:
        import tree_sitter_go  # noqa: F401
    except ImportError:
        return False
    return True


# ---------------------------------------------------------------------------
# Shell extractor
# ---------------------------------------------------------------------------


class TestContractsFastAPI:
    def test_single_route(self):
        src = textwrap.dedent(
            """
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/users")
            def list_users():
                return []
            """
        )
        r = contracts.extract("backend/app.py", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        assert any(n.label == "GET /users" for n in routes)
        handles = [e for e in r.edges if e.edge_type == "handles_route"]
        assert handles
        assert any(n.metadata.get("handler") == "list_users" for n in routes)

    def test_include_router_prefix(self):
        src = textwrap.dedent(
            """
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/items")
            def create(): pass

            app.include_router(router, prefix="/v2")
            """
        )
        r = contracts.extract("backend/app.py", src)
        mounts = [n for n in r.nodes if n.metadata.get("derivation") == "fastapi_include_router"]
        assert mounts


class TestContractsFlask:
    def test_methods_multi(self):
        src = textwrap.dedent(
            """
            @app.route("/p", methods=["GET", "POST"])
            def handler(): pass
            """
        )
        r = contracts.extract("backend/flaskapp.py", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        methods = {n.metadata.get("method") for n in routes}
        assert methods == {"get", "post"}


class TestContractsDRF:
    def test_api_view_decorator(self):
        src = textwrap.dedent(
            """
            @api_view(['GET', 'POST'])
            def my_view(request): pass
            """
        )
        r = contracts.extract("backend/views.py", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        # Expect one entry per HTTP method.
        assert len(routes) == 2
        assert all(n.metadata.get("framework") == "drf" for n in routes)

    def test_router_register_synthesises_routes(self):
        src = textwrap.dedent(
            """
            from rest_framework.routers import DefaultRouter

            router = DefaultRouter()
            router.register("users", UserViewSet)
            """
        )
        r = contracts.extract("backend/urls.py", src)
        routes = [n for n in r.nodes if n.metadata.get("derivation") == "drf_router_register"]
        # router_register synthesises 6 routes (list, create, retrieve,
        # update, partial_update, delete).
        assert len(routes) == 6
        assert all(n.metadata.get("handler") == "UserViewSet" for n in routes)


class TestContractsNextjs:
    def test_dynamic_segment(self):
        src = "export async function GET(req) { return Response.json({}); }\n"
        r = contracts.extract("frontend/app/users/[id]/route.ts", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        assert any(n.metadata.get("note") == "dynamic_segment" for n in routes)
        # Path normalised with {id}.
        assert any("/users/{id}" in (n.metadata.get("path") or "") for n in routes)

    def test_catch_all_segment(self):
        src = "export function POST(req) { return Response.json({}); }\n"
        r = contracts.extract("frontend/app/docs/[[...slug]]/route.ts", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        assert routes
        path = routes[0].metadata.get("path", "")
        assert "**" in path or "{" in path

    def test_dynamic_fetch_not_a_parse_error(self):
        # TASK-303: a template-literal fetch route is parsed fine, just not
        # statically resolvable — it must not be counted as a parse error.
        src = "const r = await fetch(`/api/${id}`);\n"
        r = contracts.extract("frontend/src/client.ts", src)
        assert not any(p.kind == "opaque_route" for p in r.parse_errors)

    def test_pages_router_api_handler(self):
        # pages-router API: default-export handler → /api/users (method any).
        src = "export default function handler(req, res) { res.json({}); }\n"
        r = contracts.extract("frontend/pages/api/users.ts", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        assert any(
            n.metadata.get("path") == "/api/users"
            and n.metadata.get("derivation") == "pages_router_api"
            for n in routes
        )

    def test_app_router_page_is_get_route(self):
        src = "export default function Page() { return <div>Dashboard</div>; }\n"
        r = contracts.extract("frontend/app/dashboard/page.tsx", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        assert any(
            n.metadata.get("path") == "/dashboard"
            and n.metadata.get("method") == "get"
            and n.metadata.get("derivation") == "nextjs_page"
            for n in routes
        )

    def test_pages_router_page_and_index(self):
        about = contracts.extract(
            "frontend/pages/about.tsx", "export default function About() { return null; }\n"
        )
        assert any(n.metadata.get("path") == "/about" for n in about.nodes if n.kind == "cos:route")
        index = contracts.extract(
            "frontend/pages/index.tsx", "export default function Home() { return null; }\n"
        )
        assert any(n.metadata.get("path") == "/" for n in index.nodes if n.kind == "cos:route")

    def test_pages_dynamic_segment(self):
        src = "export default function Post() { return null; }\n"
        r = contracts.extract("frontend/pages/blog/[slug].tsx", src)
        assert any(
            n.metadata.get("path") == "/blog/{slug}" for n in r.nodes if n.kind == "cos:route"
        )

    def test_plain_component_is_not_a_route(self):
        # A default-export component outside app/ or pages/ is NOT a route.
        src = "export default function Button() { return <button/>; }\n"
        r = contracts.extract("frontend/src/components/Button.tsx", src)
        assert [n for n in r.nodes if n.kind == "cos:route"] == []


class TestContractsMCP:
    def test_mcp_tool_decorator(self):
        src = textwrap.dedent(
            """
            @mcp.tool("cos_graph_query")
            @safe_tool
            def handler():
                pass
            """
        )
        r = contracts.extract("core/thinking_os/tools/graph.py", src)
        tools = [n for n in r.nodes if n.kind == "cos:mcp_tool"]
        assert tools
        assert tools[0].label == "mcp:cos_graph_query"


class TestContractsEvents:
    def test_celery_task(self):
        src = textwrap.dedent(
            """
            @celery_app.task(name="send_email")
            def send_email():
                pass
            """
        )
        r = contracts.extract("worker/tasks.py", src)
        events = [n for n in r.nodes if n.metadata.get("kind") == "event"]
        assert events
        assert any(n.metadata.get("framework") == "celery" for n in events)

    def test_websocket(self):
        src = '@app.sock.route("/ws/chat")\ndef chat(ws): pass\n'
        r = contracts.extract("backend/ws.py", src)
        ws = [n for n in r.nodes if n.metadata.get("kind") == "websocket"]
        assert ws


class TestContractsGoFiber:
    def test_group_prefix_per_variable(self):
        # A route on bare `app` must NOT inherit a sibling group's prefix
        # (the old `groups[-1]` bug). A route on `v1` must get `/v1`.
        src = textwrap.dedent(
            """
            import "github.com/gofiber/fiber/v2"
            app := fiber.New()
            v1 := app.Group("/v1")
            app.Get("/health", checkHealth)
            v1.Get("/users", listUsers)
            """
        )
        r = contracts.extract("backend/routes.go", src)
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert "GET /health" in labels
        assert "GET /v1/users" in labels
        assert "GET /v1/health" not in labels  # old last-group-seen bug

    def test_route_handler_edge(self):
        src = textwrap.dedent(
            """
            import "github.com/gofiber/fiber/v2"
            app := fiber.New()
            app.Get("/users", listUsers)
            """
        )
        r = contracts.extract("backend/routes.go", src)
        assert any(e.edge_type == "calls" and e.target_uid.endswith("listUsers") for e in r.edges)

    def test_nested_group_prefix(self):
        src = textwrap.dedent(
            """
            import "github.com/gofiber/fiber/v2"
            app := fiber.New()
            api := app.Group("/api")
            v2 := api.Group("/v2")
            v2.Post("/items", createItem)
            """
        )
        r = contracts.extract("backend/routes.go", src)
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert "POST /api/v2/items" in labels


class TestContractsGeneric:
    def test_non_matching_file_emits_only_file_node(self):
        r = contracts.extract("README.md", "# hello")
        routes = [n for n in r.nodes if n.kind in ("cos:route", "cos:mcp_tool")]
        assert routes == []

    def test_empty_python_file(self):
        r = contracts.extract("foo.py", "")
        assert r.parse_errors == []

    def test_dogfood_server_module(self):
        """The server.py module should expose ≥ 1 MCP tool when scanned."""
        src = textwrap.dedent(
            """
            @mcp.tool("cos_health")
            @safe_tool
            def cos_health():
                return {}

            @mcp.tool("cos_search")
            @safe_tool
            def cos_search(query):
                return {}
            """
        )
        r = contracts.extract("core/thinking_os/server.py", src)
        tools = [n for n in r.nodes if n.kind == "cos:mcp_tool"]
        assert len(tools) == 2


class TestContractsGoFrameworks:
    def test_gin(self):
        r = contracts.extract(
            "backend/server.go",
            """package main
import "github.com/gin-gonic/gin"
func main() {
  r := gin.Default()
  r.GET("/health", h)
  v1 := r.Group("/v1")
  v1.POST("/items", h2)
}""",
        )
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        labels = {n.label for n in routes}
        # Per-variable prefix: bare-r route stays /health, group route gets /v1.
        assert "GET /health" in labels
        assert "GET /v1/health" not in labels
        assert "POST /v1/items" in labels

    def test_chi(self):
        r = contracts.extract(
            "backend/server.go",
            """package main
import "github.com/go-chi/chi/v5"
func main() {
  r := chi.NewRouter()
  r.Get("/users", h)
}""",
        )
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert "GET /users" in labels

    def test_echo(self):
        r = contracts.extract(
            "backend/server.go",
            """package main
import "github.com/labstack/echo/v4"
func main() { e := echo.New(); e.GET("/", h) }""",
        )
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert "GET /" in labels

    def test_gorilla(self):
        r = contracts.extract(
            "backend/server.go",
            """package main
import "github.com/gorilla/mux"
func main() {
  r := mux.NewRouter()
  r.HandleFunc("/api/{id}", h).Methods("GET", "POST")
}""",
        )
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert "GET /api/{id}" in labels
        assert "POST /api/{id}" in labels

    def test_net_http_go122(self):
        r = contracts.extract(
            "backend/server.go",
            """package main
import "net/http"
func main() {
  http.HandleFunc("GET /status", statusH)
  http.HandleFunc("POST /webhook", hookH)
}""",
        )
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert "GET /status" in labels
        assert "POST /webhook" in labels

    def test_grpc_register(self):
        r = contracts.extract(
            "backend/server.go",
            """package main
import (
  "google.golang.org/grpc"
  pb "example.com/api/proto"
)
func main() {
  s := grpc.NewServer()
  pb.RegisterUserServer(s, &userSrv{})
}""",
        )
        labels = {n.label for n in r.nodes if n.kind == "cos:route"}
        assert any("User" in l for l in labels)

    def test_cobra_command(self):
        r = contracts.extract(
            "cmd/root.go",
            """package cmd
import "github.com/spf13/cobra"
var rootCmd = &cobra.Command{
  Use: "myapp",
  Short: "tool",
}
var serveCmd = &cobra.Command{ Use: "serve" }
""",
        )
        labels = {n.label for n in r.nodes if n.kind == "cos:cli_command"}
        assert "cobra:myapp" in labels
        assert "cobra:serve" in labels
