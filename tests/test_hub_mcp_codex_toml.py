"""Codex `[mcp_servers.*]` editing preserves the file the user maintains by hand.

The contract that matters is not "valid TOML comes out" — a parse-and-dump writer
satisfies that while silently deleting every comment. It is that the bytes the
edit did not target are unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.web.routes import _config_codex_toml as codex

REAL_SHAPE = """\
# My Codex config — keep these comments.
model = "gpt-5.6"

[projects."/Users/me/work"]
trust_level = "trusted"

[mcp_servers.firecrawl]
command = "npx"
args = ["-y", "firecrawl-mcp"]

[mcp_servers.firecrawl.env]
FIRECRAWL_API_KEY = "dummy"

[mcp_servers.node_repl]
args = []
command = "/opt/node_repl"
startup_timeout_sec = 120
"""


@pytest.fixture()
def config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(REAL_SHAPE, encoding="utf-8")
    return path


class TestRead:
    def test_reads_each_server_with_its_top_level_keys(self, config: Path) -> None:
        servers = codex.read_servers(config)

        assert set(servers) == {"firecrawl", "node_repl"}
        assert servers["firecrawl"]["command"] == "npx"
        assert servers["node_repl"]["startup_timeout_sec"] == "120"

    def test_env_subtable_keys_do_not_leak_into_the_parent(self, config: Path) -> None:
        # [mcp_servers.firecrawl.env] keys belong to the sub-table; hoisting them
        # would report a server with an API key as a top-level field.
        assert "FIRECRAWL_API_KEY" not in codex.read_servers(config)["firecrawl"]

    def test_keys_after_an_unrelated_table_are_not_attributed_to_a_server(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "c.toml"
        path.write_text(
            '[mcp_servers.a]\ncommand = "x"\n\n[history]\npersistence = "none"\n', encoding="utf-8"
        )
        assert codex.read_servers(path) == {"a": {"command": "x"}}

    def test_a_missing_file_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert codex.read_servers(tmp_path / "absent.toml") == {}


class TestWrite:
    def test_appending_leaves_every_existing_byte_untouched(self, config: Path) -> None:
        before = config.read_text(encoding="utf-8")

        codex.write_server(config, "playwright", {"command": "npx", "args": ["-y", "@pw/mcp"]})

        after = config.read_text(encoding="utf-8")
        assert after.startswith(before.rstrip("\n"))
        assert "# My Codex config — keep these comments." in after
        assert '[mcp_servers.playwright]\ncommand = "npx"\nargs = ["-y", "@pw/mcp"]' in after

    def test_the_new_server_reads_back(self, config: Path) -> None:
        codex.write_server(config, "playwright", {"command": "npx", "args": []})
        assert codex.read_servers(config)["playwright"]["command"] == "npx"

    def test_writes_an_env_subtable_when_one_is_given(self, config: Path) -> None:
        codex.write_server(config, "srv", {"command": "x", "env": {"TOKEN": "t"}})
        text = config.read_text(encoding="utf-8")
        assert "[mcp_servers.srv.env]" in text
        assert 'TOKEN = "t"' in text

    def test_rewriting_an_existing_server_replaces_it_in_place(self, config: Path) -> None:
        codex.write_server(config, "firecrawl", {"command": "uvx", "args": ["fc"]})
        text = config.read_text(encoding="utf-8")

        assert text.count("[mcp_servers.firecrawl]") == 1
        assert codex.read_servers(config)["firecrawl"]["command"] == "uvx"
        # The replaced block took its own env sub-table with it, not the next
        # server's — node_repl must survive intact.
        assert codex.read_servers(config)["node_repl"]["command"] == "/opt/node_repl"

    def test_creates_the_file_when_none_exists(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "config.toml"
        codex.write_server(path, "srv", {"command": "npx"})
        assert codex.read_servers(path) == {"srv": {"command": "npx"}}


class TestRemove:
    def test_removes_a_server_and_its_env_subtable(self, config: Path) -> None:
        assert codex.remove_server(config, "firecrawl") is True

        text = config.read_text(encoding="utf-8")
        assert "mcp_servers.firecrawl" not in text
        assert "FIRECRAWL_API_KEY" not in text
        assert "# My Codex config — keep these comments." in text
        assert codex.read_servers(config)["node_repl"]["command"] == "/opt/node_repl"

    def test_removing_the_last_table_keeps_the_preamble(self, config: Path) -> None:
        codex.remove_server(config, "firecrawl")
        codex.remove_server(config, "node_repl")

        text = config.read_text(encoding="utf-8")
        assert codex.read_servers(config) == {}
        assert 'model = "gpt-5.6"' in text
        assert '[projects."/Users/me/work"]' in text

    def test_an_unknown_server_reports_false_and_changes_nothing(self, config: Path) -> None:
        before = config.read_text(encoding="utf-8")
        assert codex.remove_server(config, "nope") is False
        assert config.read_text(encoding="utf-8") == before


class TestRouteWiring:
    """The routes import their helpers lazily, so a rename type-checks and passes
    every unit test while returning 500 to the first real request. Importing the
    route modules and resolving those names is what catches it."""

    def test_the_mcp_route_returns_a_well_formed_payload(self, tmp_path, monkeypatch) -> None:
        from core.web.routes import _config_mcp, _config_read

        monkeypatch.setattr(_config_read, "_project_root", lambda: tmp_path)
        monkeypatch.setattr(_config_mcp, "codex_config_path", lambda: tmp_path / "none.toml")

        payload = _config_read.config_mcp()

        assert set(payload) == {"servers", "count", "scopes", "adapters"}
        assert set(payload["adapters"]) == set(_config_mcp.MANAGED_ADAPTERS)


class TestRefusal:
    def test_refuses_an_inline_mcp_servers_table(self, tmp_path: Path) -> None:
        # Corrupting a config is worse than declining to edit it.
        path = tmp_path / "c.toml"
        path.write_text('mcp_servers = { a = { command = "x" } }\n', encoding="utf-8")

        with pytest.raises(codex.UnsupportedShape, match="edit it by hand"):
            codex.write_server(path, "b", {"command": "y"})
        assert codex.read_servers(path) == {}
