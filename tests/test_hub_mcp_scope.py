"""Hub MCP inventory: scope, transport, and custom-server writes.

Grounded in a survey of this machine's real configs: 3 servers declared globally
were invisible to the project-scoped reader, and 6 of 14 project servers use an
HTTP/SSE transport that a command+args-only reader renders as a blank row.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.web.routes import _config_mcp as mcp


def _write_config(path: Path, servers: dict, **extra) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers, **extra}, indent=2), encoding="utf-8")
    return path


class TestTransportClassification:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ({"command": "npx", "args": ["-y", "x"]}, "stdio"),
            ({"type": "http", "url": "https://example.com/mcp"}, "http"),
            ({"type": "sse", "url": "https://example.com/sse"}, "sse"),
            # A url with no declared type is still remote — the real posthog and
            # vercel entries on this machine are shaped exactly like this.
            ({"url": "https://example.com/mcp"}, "http"),
            ({"type": "HTTP", "url": "https://example.com"}, "http"),
        ],
    )
    def test_classifies_the_transport(self, spec: dict, expected: str) -> None:
        assert mcp.describe_transport(spec) == expected


class TestInventory:
    def test_lists_project_and_global_each_labelled_by_scope(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        _write_config(project / ".mcp.json", {"supabase": {"type": "http", "url": "https://s"}})
        global_path = _write_config(
            tmp_path / "home" / ".claude.json", {"firecrawl": {"command": "npx", "args": []}}
        )

        rows = mcp.inventory(project, global_path=global_path)

        assert [(r["name"], r["scope"]) for r in rows] == [
            ("supabase", "project"),
            ("firecrawl", "global"),
        ]

    def test_a_remote_server_keeps_its_url_instead_of_a_blank_command(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        _write_config(project / ".mcp.json", {"posthog": {"type": "http", "url": "https://p/mcp"}})

        row = mcp.inventory(project, global_path=tmp_path / "absent.json")[0]

        assert row["transport"] == "http"
        assert row["url"] == "https://p/mcp"
        assert row["command"] is None

    def test_flags_a_global_server_shadowed_by_a_project_entry(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        _write_config(project / ".mcp.json", {"playwright": {"command": "npx", "args": []}})
        global_path = _write_config(
            tmp_path / "home" / ".claude.json", {"playwright": {"command": "npx", "args": []}}
        )

        rows = mcp.inventory(project, global_path=global_path)
        shadowed = next(r for r in rows if r["scope"] == "global")

        assert shadowed["shadowed_by_project"] is True

    def test_a_missing_or_unreadable_file_is_an_empty_scope_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        project = tmp_path / "proj"
        (project).mkdir()
        (project / ".mcp.json").write_text("{ not json", encoding="utf-8")

        assert mcp.inventory(project, global_path=tmp_path / "nope.json") == []


class TestValidation:
    @pytest.mark.parametrize(
        ("spec", "fragment"),
        [
            ({}, "needs a command"),
            ({"command": "   "}, "needs a command"),
            ({"type": "http"}, "needs a url"),
            ({"type": "http", "url": "ftp://x"}, "http:// or https://"),
            ({"command": "npx", "args": "not-a-list"}, "args must be a list"),
        ],
    )
    def test_rejects_an_unusable_spec_with_a_human_reason(self, spec: dict, fragment: str) -> None:
        assert fragment in (mcp.validate_server_spec("srv", spec) or "")

    @pytest.mark.parametrize(
        "spec",
        [
            {"command": "npx", "args": ["-y", "pkg"]},
            {"type": "http", "url": "https://example.com/mcp"},
            {"type": "sse", "url": "http://localhost:3002/sse"},
        ],
    )
    def test_accepts_both_transports(self, spec: dict) -> None:
        assert mcp.validate_server_spec("srv", spec) is None

    def test_an_empty_name_is_rejected(self) -> None:
        assert mcp.validate_server_spec("", {"command": "npx"}) == "server name is required"


class TestNormalize:
    def test_keeps_only_the_keys_the_transport_uses(self) -> None:
        assert mcp.normalize_server_spec({"command": " npx ", "args": ["-y"]}) == {
            "command": "npx",
            "args": ["-y"],
        }
        assert mcp.normalize_server_spec({"type": "sse", "url": " https://x/sse "}) == {
            "type": "sse",
            "url": "https://x/sse",
        }

    def test_a_url_wins_over_a_stray_command(self) -> None:
        # A spec carrying both is remote: the url is the thing that can actually
        # be reached, and writing a command a remote server ignores is a lie in
        # the config file.
        assert mcp.normalize_server_spec({"command": "npx", "url": "https://x"}) == {
            "type": "http",
            "url": "https://x",
        }

    def test_carries_env_and_headers_when_present(self) -> None:
        assert mcp.normalize_server_spec({"command": "npx", "env": {"K": "v"}})["env"] == {"K": "v"}
        assert mcp.normalize_server_spec(
            {"type": "http", "url": "https://x", "headers": {"Authorization": "Bearer t"}}
        )["headers"] == {"Authorization": "Bearer t"}


class TestWrites:
    def test_writing_preserves_every_other_key_in_the_file(self, tmp_path: Path) -> None:
        # The global config holds unrelated user state; a writer that rebuilt the
        # document would silently delete it.
        path = _write_config(
            tmp_path / ".claude.json", {"existing": {"command": "a"}}, numStartups=42
        )

        mcp.write_server(path, "added", {"type": "http", "url": "https://x"})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["numStartups"] == 42
        assert set(data["mcpServers"]) == {"existing", "added"}

    def test_writes_into_a_file_that_does_not_exist_yet(self, tmp_path: Path) -> None:
        path = tmp_path / "fresh" / ".mcp.json"
        mcp.write_server(path, "srv", {"command": "npx", "args": []})
        assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["srv"]["command"] == "npx"

    def test_a_malformed_file_raises_instead_of_overwriting_it(self, tmp_path: Path) -> None:
        path = tmp_path / ".mcp.json"
        path.write_text("{ not json", encoding="utf-8")

        with pytest.raises(ValueError, match="not readable JSON"):
            mcp.write_server(path, "srv", {"command": "npx"})
        assert path.read_text(encoding="utf-8") == "{ not json"

    def test_remove_reports_whether_it_removed_anything(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path / ".mcp.json", {"srv": {"command": "npx"}})

        assert mcp.remove_server(path, "srv") is True
        assert mcp.remove_server(path, "srv") is False
        assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"] == {}


class TestScopeRouting:
    def test_scope_selects_the_config_file(self, tmp_path: Path) -> None:
        global_path = tmp_path / "home" / ".claude.json"
        assert mcp.config_path_for_scope(tmp_path, "project") == tmp_path / ".mcp.json"
        assert mcp.config_path_for_scope(tmp_path, "global", global_path=global_path) == global_path

    def test_the_route_default_matches_the_module_constant(self) -> None:
        # The FastAPI query default cannot import at call time, so the literal is
        # duplicated in the route module; this is the guard that they agree.
        from core.web.routes._config_mutate import PROJECT_SCOPE_DEFAULT

        assert PROJECT_SCOPE_DEFAULT == mcp.PROJECT_SCOPE
