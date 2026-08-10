"""Leaf: the ContractMatch record and the helpers every scanner family needs."""

from __future__ import annotations

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
