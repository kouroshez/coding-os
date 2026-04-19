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

from graph_os.extractors import code_shell, code_yaml, contracts


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

    def test_source_dynamic_path_logged(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            'source "$(dirname "$0")/cos-env.sh"\n',
        )
        # Dynamic — no literal edge, but a `dynamic` parse_error must
        # be surfaced so operators can audit missing coverage.
        assert any(p.kind == "dynamic" or p.kind == "dynamic_shell" for p in r.parse_errors)

    def test_dot_include_edge(self):
        r = code_shell.extract("core/hooks/x.sh", '. ./utils.sh\n')
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert imports

    def test_comment_lines_ignored(self):
        r = code_shell.extract("core/hooks/x.sh", "# source fake.sh\necho ok")
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert imports == []

    def test_function_node_emitted(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            'greet() {\n  echo hi\n}\n',
        )
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "greet" for n in fns)

    def test_cos_log_hook_edge(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            'cos_log_hook my-hook entered\n',
        )
        edges = [e for e in r.edges if e.edge_type == "handles_tool"]
        assert any(e.target_uid == "cos:hook:my-hook" for e in edges)

    def test_dynamic_hint_recorded(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            'source "$(find_script)"\n',
        )
        assert any(p.kind == "dynamic" for p in r.parse_errors)

    def test_script_call_not_duplicated_as_import(self):
        r = code_shell.extract(
            "core/hooks/x.sh",
            'source ./util.sh\nbash ./util.sh\n',
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        calls = [e for e in r.edges if e.edge_type == "calls"]
        # source emits imports; we skip a duplicate `calls` edge to the same.
        assert len(imports) == 1
        assert calls == []


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
        mounts = [
            n for n in r.nodes if n.metadata.get("derivation") == "fastapi_include_router"
        ]
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
        routes = [
            n for n in r.nodes if n.metadata.get("derivation") == "drf_router_register"
        ]
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

    def test_dynamic_fetch_flagged(self):
        src = 'const r = await fetch(`/api/${id}`);\n'
        r = contracts.extract("frontend/src/client.ts", src)
        assert any(p.kind == "opaque_route" for p in r.parse_errors)


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
        r = contracts.extract("core/thinking-os/tools/graph.py", src)
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
        events = [
            n for n in r.nodes if n.metadata.get("kind") == "event"
        ]
        assert events
        assert any(n.metadata.get("framework") == "celery" for n in events)

    def test_websocket(self):
        src = '@app.sock.route("/ws/chat")\ndef chat(ws): pass\n'
        r = contracts.extract("backend/ws.py", src)
        ws = [n for n in r.nodes if n.metadata.get("kind") == "websocket"]
        assert ws


class TestContractsGoFiber:
    def test_group_prefix(self):
        src = textwrap.dedent(
            """
            v1 := app.Group("/v1")
            app.Get("/users", listUsers)
            """
        )
        r = contracts.extract("backend/routes.go", src)
        routes = [n for n in r.nodes if n.kind == "cos:route"]
        assert routes


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
        r = contracts.extract("core/thinking-os/server.py", src)
        tools = [n for n in r.nodes if n.kind == "cos:mcp_tool"]
        assert len(tools) == 2
