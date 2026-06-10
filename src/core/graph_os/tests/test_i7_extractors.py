"""I.7 tests — shell + yaml + contracts extractors.

Ship gate (Section 19 I.7):
  - full coding-os hook graph visible
  - cos-env.sh inbound edges ≥ 30
  - contracts detector finds all 21 MCP tools
  - external fixture: DRF / FastAPI / Next.js dynamic routes
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_go, code_json, code_shell, code_toml, code_yaml, contracts


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


class TestShellExtractor:
    def test_file_node_emitted(self):
        r = code_shell.extract("core/hooks/x.sh", "#!/usr/bin/env bash\necho hi\n")
        assert any(n.kind == "code:file" for n in r.nodes)

    def test_source_edge(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            "source core/hooks/cos-env.sh\n",
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert any("cos-env.sh" in e.target_uid for e in imports)

    def test_dirname_self_resolves_to_script_dir(self):
        # The very common `$(dirname "$0")/X` idiom resolves to a concrete
        # uid relative to the script's own directory (code_shell@v2).
        r = code_shell.extract(
            "core/hooks/x.sh",
            'source "$(dirname "$0")/cos-env.sh"\n',
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert any("cos-env.sh" in e.target_uid for e in imports)

    def test_dot_include_edge(self):
        r = code_shell.extract("core/hooks/x.sh", ". ./utils.sh\n")
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert imports

    def test_comment_lines_ignored(self):
        r = code_shell.extract("core/hooks/x.sh", "# source fake.sh\necho ok")
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert imports == []

    def test_function_node_emitted(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            "greet() {\n  echo hi\n}\n",
        )
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "greet" for n in fns)

    def test_cos_log_hook_edge(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            "cos_log_hook my-hook entered\n",
        )
        edges = [e for e in r.edges if e.edge_type == "handles_tool"]
        assert any(e.target_uid == "cos:hook:my-hook" for e in edges)

    def test_dynamic_source_not_recorded_as_parse_error(self):
        # TASK-303: an unresolvable dynamic source is expected and parsed
        # cleanly — it must not appear as a parse error.
        r = code_shell.extract(
            "core/hooks/x.sh",
            'source "$(find_script)"\n',
        )
        assert not any(p.kind == "dynamic" for p in r.parse_errors)

    def test_script_call_not_duplicated_as_import(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            "source ./util.sh\nbash ./util.sh\n",
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        calls = [e for e in r.edges if e.edge_type == "calls"]
        # source emits imports; we skip a duplicate `calls` edge to the same.
        assert len(imports) == 1
        assert calls == []

    def test_function_inside_heredoc_not_matched(self):
        # Tree-sitter-bash classifies heredoc bodies as raw text — function
        # definitions inside must not become graph nodes.
        src = "real_func() { echo real; }\ncat <<EOF\nfake_inside_heredoc() { echo nope; }\nEOF\n"
        r = code_shell.extract("core/hooks/x.sh", src)
        names = {n.label for n in r.nodes if n.kind == "code:function"}
        assert "real_func" in names
        assert "fake_inside_heredoc" not in names


# ---------------------------------------------------------------------------
# YAML extractor
# ---------------------------------------------------------------------------


class TestYamlExtractor:
    def test_emits_file_and_keys(self):
        r = code_yaml.extract(
            "core/hooks/registry.yaml",
            textwrap.dedent(
                """
                name: enforce-doc-anchor
                event: PreToolUse
                matcher: Edit|Write
                category: safety
                """
            ),
        )
        keys = {n.metadata.get("key") for n in r.nodes if n.kind == "doc:frontmatter_key"}
        assert {"name", "event", "matcher", "category"} <= keys

    def test_nested_structure_walked(self):
        r = code_yaml.extract(
            "core/rag-config.yaml",
            textwrap.dedent(
                """
                graph:
                  backend: auto
                  lsp:
                    enabled: true
                """
            ),
        )
        paths = {n.metadata.get("path") for n in r.nodes if n.kind == "doc:frontmatter_key"}
        assert "graph" in paths
        assert "graph.backend" in paths
        assert "graph.lsp.enabled" in paths

    def test_references_edges_emitted_for_known_keys(self):
        r = code_yaml.extract(
            "core/rules/memory.yaml",
            "ssot_of: docs/governance/memory.md\n",
        )
        edges = [e for e in r.edges if e.edge_type == "ssot_of"]
        assert edges and edges[0].target_uid == "doc:file:docs/governance/memory.md"

    def test_list_values_emit_multiple_edges(self):
        r = code_yaml.extract(
            "core/stacks/example.yaml",
            textwrap.dedent(
                """
                rules:
                  - docs/engineering/rule-a.md
                  - docs/engineering/rule-b.md
                """
            ),
        )
        refs = [e for e in r.edges if e.edge_type == "references_doc"]
        assert len(refs) == 2

    def test_invalid_yaml_does_not_crash(self):
        # `key: value: also:` is ambiguous YAML mapping syntax — PyYAML
        # raises a ParserError we catch.
        r = code_yaml.extract("bad.yaml", "key: value\n  nested: 'unclosed\n")
        assert any(p.kind == "yaml_parse_error" for p in r.parse_errors)

    def test_empty_file(self):
        r = code_yaml.extract("empty.yaml", "")
        assert r.parse_errors == []
        assert any(n.kind == "code:file" for n in r.nodes)


# ---------------------------------------------------------------------------
# Contracts extractor
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


# ---------------------------------------------------------------------------
# JSON extractor
# ---------------------------------------------------------------------------


class TestJsonExtractor:
    def test_package_json_deps_and_scripts(self):
        src = """{
  \"name\": \"web\",
  \"dependencies\": {\"react\": \"^18\", \"next\": \"^14\"},
  \"devDependencies\": {\"vitest\": \"^1\"},
  \"scripts\": {\"build\": \"next build\", \"dev\": \"next dev\"}
}"""
        r = code_json.extract("apps/web/package.json", src)
        assert any(n.uid == "npm:package:web" for n in r.nodes)
        dep_targets = {e.target_uid for e in r.edges if e.edge_type == "imports"}
        assert "npm:package:react" in dep_targets
        assert "npm:package:next" in dep_targets
        assert "npm:package:vitest" in dep_targets
        script_labels = {n.label for n in r.nodes if n.kind == "tool"}
        assert {"npm:build", "npm:dev"} <= script_labels
        assert len(r.parse_errors) == 0

    def test_tsconfig_extends_and_paths(self):
        src = """{
  // line comment OK
  \"extends\": \"./base.json\",
  \"compilerOptions\": {\n    \"paths\": { \"@app/*\": [\"src/*\"] }
  },
}"""
        r = code_json.extract("apps/web/tsconfig.json", src)
        assert any("base.json" in e.target_uid for e in r.edges if e.edge_type == "imports")
        assert any(n.label == "@app/*" for n in r.nodes if n.kind == "contract")
        assert len(r.parse_errors) == 0

    def test_mcp_json_servers(self):
        src = """{ "mcpServers": { "coding-os": { "command": "cos" }, "other": {} } }"""
        r = code_json.extract(".mcp.json", src)
        srv_uids = {n.uid for n in r.nodes if n.uid.startswith("mcp:server:")}
        assert srv_uids == {"mcp:server:coding-os", "mcp:server:other"}

    def test_settings_json_hook_events(self):
        src = """{ "hooks": { "PreToolUse": [], "SessionStart": [] } }"""
        r = code_json.extract(".claude/settings.json", src)
        events = {n.label for n in r.nodes if n.kind == "event"}
        assert events == {"PreToolUse", "SessionStart"}

    def test_malformed_json_falls_back_to_file_node(self):
        r = code_json.extract("broken.json", "{not json}")
        assert any(p.kind == "json_decode" for p in r.parse_errors)
        assert any(n.uid == "code:file:broken.json" for n in r.nodes)


# ---------------------------------------------------------------------------
# TOML extractor
# ---------------------------------------------------------------------------


class TestTomlExtractor:
    def test_pyproject_project_and_deps(self):
        src = """[project]
name = "coding-os"
dependencies = ["click>=8.0", "pyyaml", "anthropic[bedrock]"]

[project.scripts]
cos = "cli.main:cli"
"""
        r = code_toml.extract("pyproject.toml", src)
        assert any(n.uid == "pypi:package:coding-os" for n in r.nodes)
        dep_targets = {e.target_uid for e in r.edges if e.edge_type == "imports"}
        assert "pypi:package:click" in dep_targets
        assert "pypi:package:pyyaml" in dep_targets
        assert "pypi:package:anthropic" in dep_targets
        assert any(n.label == "cos" for n in r.nodes if n.kind == "tool")
        assert len(r.parse_errors) == 0

    def test_cargo_package_and_deps(self):
        src = """[package]
name = "agent"
version = "0.1"

[dependencies]
tokio = "1"
serde = { version = "1", features = ["derive"] }

[workspace]
members = ["crates/core", "crates/util"]
"""
        r = code_toml.extract("Cargo.toml", src)
        assert any(n.uid == "crates:package:agent" for n in r.nodes)
        dep_targets = {e.target_uid for e in r.edges if e.edge_type == "imports"}
        assert "crates:package:tokio" in dep_targets
        assert "crates:package:serde" in dep_targets
        workspace_targets = {
            e.target_uid for e in r.edges if e.target_uid.startswith("folder:crates")
        }
        assert "folder:crates/core" in workspace_targets
        assert "folder:crates/util" in workspace_targets

    def test_malformed_toml_falls_back(self):
        r = code_toml.extract("broken.toml", "this is not [valid")
        assert any(p.kind == "toml_decode" for p in r.parse_errors)
        assert any(n.uid == "code:file:broken.toml" for n in r.nodes)


# ---------------------------------------------------------------------------
# Go extractor
# ---------------------------------------------------------------------------


class TestGoExtractor:
    def test_package_and_file_nodes(self):
        r = code_go.extract("server/handler.go", "package server\n")
        kinds = {n.kind for n in r.nodes}
        assert "code:file" in kinds
        assert "code:module" in kinds
        assert "code:package" in kinds
        pkg_nodes = [n for n in r.nodes if n.kind == "code:package"]
        assert pkg_nodes[0].label == "server"

    def test_function_node(self):
        r = code_go.extract(
            "server/handler.go", 'package server\nfunc Hello() string { return "" }\n'
        )
        funcs = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "Hello" for n in funcs)

    def test_method_node_with_pointer_receiver(self):
        r = code_go.extract(
            "server/handler.go",
            "package server\ntype S struct{}\nfunc (s *S) Do() {}\n",
        )
        methods = [n for n in r.nodes if n.kind == "code:method"]
        assert any(n.label == "S.Do" for n in methods)

    def test_method_receiver_uid_strips_generics(self):
        r = code_go.extract(
            "p/x.go",
            "package p\ntype Container[T any] struct{}\nfunc (c *Container[T]) Add(item T) {}\n",
        )
        methods = [n for n in r.nodes if n.kind == "code:method"]
        assert any(n.label == "Container.Add" for n in methods)

    @pytest.mark.skipif(
        not _go_ts_available(),
        reason="tree-sitter-go grammar not installed (AST-driven Go extractor needed for embedded edges).",
    )
    def test_struct_field_and_embedded_edges(self):
        r = code_go.extract(
            "p/x.go",
            """package p
type Reader interface{}
type Inner struct{}
type Server struct {
    Reader
    Conn Inner
}
""",
        )
        embedded = [e for e in r.edges if e.edge_type == "inherits_from"]
        fields = [e for e in r.edges if e.edge_type == "field_of_type"]
        # Embedded `Reader` (anonymous field) → inherits_from edge.
        assert any("Reader" in e.target_uid for e in embedded)
        # Named field `Conn Inner` → field_of_type edge to Inner (non-builtin).
        assert any("Inner" in e.target_uid for e in fields)

    @pytest.mark.skipif(
        not _go_ts_available(),
        reason="tree-sitter-go grammar not installed (AST-driven Go extractor needed for interface embedding).",
    )
    def test_interface_embedding_edge(self):
        r = code_go.extract(
            "p/x.go",
            'package p\nimport "io"\ntype RC interface { io.Reader; io.Closer }\n',
        )
        inh = [e for e in r.edges if e.edge_type == "inherits_from"]
        labels = [e.target_uid for e in inh]
        assert any("io.Reader" in s for s in labels)
        assert any("io.Closer" in s for s in labels)

    def test_imports_dot_blank_alias(self):
        r = code_go.extract(
            "p/x.go",
            """package p
import (
    "fmt"
    _ "net/http/pprof"
    . "strings"
    pb "example.com/api"
)
""",
        )
        ext = {n.label: (n.metadata or {}) for n in r.nodes if n.kind == "code:external"}
        assert "fmt" in ext
        assert ext["net/http/pprof"].get("blank_import") is True
        assert ext["strings"].get("dot_import") is True
        assert ext["example.com/api"].get("alias") == "pb"

    @pytest.mark.skipif(
        not _go_ts_available(),
        reason="tree-sitter-go grammar not installed (AST-driven const/var metadata).",
    )
    def test_const_and_var_nodes(self):
        r = code_go.extract(
            "p/x.go",
            'package p\nconst Version = "1"\nvar DefaultPort = 8080\n',
        )
        vars_ = [n for n in r.nodes if n.kind == "code:variable"]
        names = {n.label: (n.metadata or {}).get("go_kind") for n in vars_}
        assert names.get("Version") == "const"
        assert names.get("DefaultPort") == "var"

    def test_init_function_flag(self):
        r = code_go.extract("p/x.go", "package p\nfunc init() {}\n")
        init_funcs = [n for n in r.nodes if n.kind == "code:function" and n.label == "init"]
        assert init_funcs
        assert (init_funcs[0].metadata or {}).get("init") is True

    def test_test_kind_metadata(self):
        r = code_go.extract(
            "p/x_test.go",
            """package p
import "testing"
func TestFoo(t *testing.T) {}
func BenchmarkBar(b *testing.B) {}
func ExampleBaz() {}
func FuzzQux(f *testing.F) {}
func TestMain(m *testing.M) {}
""",
        )
        kinds = {
            n.label: (n.metadata or {}).get("test_kind")
            for n in r.nodes
            if n.kind == "code:function"
        }
        assert kinds["TestFoo"] == "test"
        assert kinds["BenchmarkBar"] == "benchmark"
        assert kinds["ExampleBaz"] == "example"
        assert kinds["FuzzQux"] == "fuzz"
        assert kinds["TestMain"] == "test_main"

    def test_build_tag_edge(self):
        r = code_go.extract("p/x.go", "//go:build linux && !cgo\n\npackage p\n")
        deco = [e for e in r.edges if e.edge_type == "is_decorated_by"]
        assert deco
        assert any("linux && !cgo" in e.target_uid for e in deco)

    @pytest.mark.skipif(
        not _go_ts_available(),
        reason="tree-sitter-go grammar not installed (AST-driven generic metadata).",
    )
    def test_generic_function_marked(self):
        r = code_go.extract(
            "p/x.go",
            "package p\nfunc Map[T any, U any](xs []T, f func(T) U) []U { return nil }\n",
        )
        funcs = [n for n in r.nodes if n.kind == "code:function" and n.label == "Map"]
        assert funcs
        assert (funcs[0].metadata or {}).get("generic") is True


# ---------------------------------------------------------------------------
# Go contracts (gin/echo/chi/gorilla/cobra/grpc/net_http)
# ---------------------------------------------------------------------------


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
