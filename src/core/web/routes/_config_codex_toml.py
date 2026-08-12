"""Read and edit Codex's `[mcp_servers.*]` tables without reformatting the file.

One reason to change: how Codex declares MCP servers on disk.

Deliberately NOT a TOML round-trip. `tomllib` is read-only and absent on 3.10,
and every writer that parses-then-dumps discards the comments and key order in a
file the user maintains by hand. A table can appear anywhere in a TOML document,
so an append adds one and a span delete removes one — both leave every other byte
untouched. Anything this module cannot recognise it refuses rather than rewrites.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE_PREFIX = "mcp_servers"
# `[mcp_servers.<name>]` — the server itself. `[mcp_servers.<name>.env]` and any
# deeper table belongs to it and travels with it on delete.
_TABLE_RE = re.compile(r"^\[\s*mcp_servers\.(?P<name>[A-Za-z0-9_-]+)\s*(?P<sub>\.[^\]]+)?\]\s*$")
_ANY_TABLE_RE = re.compile(r"^\[")
# An inline `mcp_servers = { … }` expresses the same servers in a shape this
# line editor cannot safely split; detected so we refuse instead of corrupting.
_INLINE_RE = re.compile(r"^\s*mcp_servers\s*=")
_SCALAR_RE = re.compile(r"^\s*(?P<key>[A-Za-z0-9_-]+)\s*=\s*(?P<value>.+?)\s*$")


class UnsupportedShape(Exception):
    """The file uses a construct this line editor will not rewrite."""


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _guard(lines: list[str]) -> None:
    for line in lines:
        if _INLINE_RE.match(line):
            raise UnsupportedShape(
                "config.toml declares mcp_servers inline; edit it by hand so no formatting is lost"
            )


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_value(raw: str):
    """A TOML scalar or single-line array as the Python value callers expect.

    Returning the array `["-y", "pkg"]` as a *string* is the shape that made a
    downstream `list(...)` split it into single characters — a value that reads
    fine in a log and is wrong everywhere it is used.
    """
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_unquote(item) for item in inner.split(",") if item.strip()]
    return _unquote(raw)


def read_servers(path: Path) -> dict[str, dict]:
    """Every `[mcp_servers.<name>]` table with its top-level scalar keys."""
    if not path.exists():
        return {}
    try:
        lines = _lines(path)
        _guard(lines)
    except (OSError, UnsupportedShape) as exc:
        logger.debug("codex config unreadable: %s", exc)
        return {}

    servers: dict[str, dict] = {}
    current: str | None = None
    for line in lines:
        table = _TABLE_RE.match(line)
        if table:
            # A sub-table (.env) keeps the parent selected but contributes no
            # top-level keys of its own.
            current = table.group("name") if not table.group("sub") else None
            if table.group("name") not in servers:
                servers[table.group("name")] = {}
            continue
        if _ANY_TABLE_RE.match(line):
            current = None
            continue
        if current is None:
            continue
        scalar = _SCALAR_RE.match(line)
        if scalar:
            servers[current][scalar.group("key")] = _parse_value(scalar.group("value"))
    return servers


def _table_span(lines: list[str], name: str) -> tuple[int, int] | None:
    """[start, end) covering the server's table and every sub-table under it."""
    start = None
    for index, line in enumerate(lines):
        table = _TABLE_RE.match(line)
        if table and table.group("name") == name and not table.group("sub"):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        table = _TABLE_RE.match(lines[index])
        if table and table.group("name") == name:
            continue  # a sub-table of this server — still ours
        if _ANY_TABLE_RE.match(lines[index]):
            end = index
            break
    # Trailing blank lines belong to the block being removed, not to its successor.
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return start, end


def _render(name: str, spec: dict) -> list[str]:
    def literal(value) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(f'"{v}"' for v in value) + "]"
        return f'"{value}"'

    block = [f"[{TABLE_PREFIX}.{name}]"]
    env = spec.get("env") if isinstance(spec.get("env"), dict) else None
    for key, value in spec.items():
        if key == "env":
            continue
        block.append(f"{key} = {literal(value)}")
    if env:
        block.append("")
        block.append(f"[{TABLE_PREFIX}.{name}.env]")
        block.extend(f'{k} = "{v}"' for k, v in env.items())
    return block


def write_server(path: Path, name: str, spec: dict) -> None:
    """Append (or replace in place) one server table, leaving the rest byte-identical."""
    lines = _lines(path) if path.exists() else []
    _guard(lines)
    span = _table_span(lines, name)
    block = _render(name, spec)
    if span is not None:
        lines[span[0] : span[1]] = block
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remove_server(path: Path, name: str) -> bool:
    """Delete one server's tables. Returns False when it was not declared."""
    if not path.exists():
        return False
    lines = _lines(path)
    _guard(lines)
    span = _table_span(lines, name)
    if span is None:
        return False
    del lines[span[0] : span[1]]
    while lines and not lines[-1].strip():
        lines.pop()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
