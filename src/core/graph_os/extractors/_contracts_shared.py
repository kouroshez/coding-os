"""Leaf: the ContractMatch record and the helpers every scanner family needs."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_STRING_CAPTURE = r"""['"](?P<path>[^'"]+)['"]"""


@dataclass(frozen=True)
class ContractMatch:
    kind: str  # "http" | "mcp" | "grpc" | "event" | "websocket" | "cli"
    framework: str  # "fastapi", "drf", "flask", "django", "celery", ...
    method: str  # HTTP method or event name or "rpc"
    path: str  # raw specifier
    handler: str | None  # best-guess function / class symbol
    line: int
    note: str | None = None
    confidence: float = 0.9
    derivation: str | None = None  # e.g. "drf_router_register"


def _line_of(content: str, idx: int) -> int:
    return content[:idx].count("\n") + 1


def _join_paths(a: str, b: str) -> str:
    a = a.rstrip("/")
    b = b.strip()
    if not b.startswith("/"):
        b = "/" + b
    return f"{a}{b}"


def _parse_method_list(raw: str) -> list[str]:
    methods: list[str] = []
    for part in raw.split(","):
        cleaned = part.strip().strip("'\"")
        if cleaned:
            methods.append(cleaned)
    return methods


def _next_def_name(content: str, start: int) -> str | None:
    """Find the next `def name(` after `start` — the decorated handler."""
    match = re.search(r"\s*def\s+([A-Za-z_][\w]*)", content[start:])
    return match.group(1) if match else None


def _python_file_docstring(content: str) -> str | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    return ast.get_docstring(tree)
