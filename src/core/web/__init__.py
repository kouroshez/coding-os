"""core.web — Unified HTTP backbone for graph_os (S4)."""

from .server import create_app, run_server

__all__ = ["create_app", "run_server"]
