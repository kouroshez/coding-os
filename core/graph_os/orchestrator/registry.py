"""Orchestrator role catalog (I.9).

PURPOSE:  Centralise the "what thinking-os roles exist?" question.
          Each role is a typed unit of work with a name, handler, and
          an optional metadata blob. The dispatcher routes tasks to
          roles by name.
INPUT:    role definitions registered via `RoleRegistry.register`.
OUTPUT:   resolved Role instances for the dispatcher.
DEPENDS:  stdlib only.
NOTES:    In I.9 we ship three canonical roles:
            - indexer:graph-os      — run extractors on a file batch
            - lsp:warm-start        — attach the shared pyright driver
            - migrator:embeddings   — the I.1 re-embed background task
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RoleContext:
    """State handed to a role handler at dispatch time.

    PURPOSE:  Loose-typed bag of references (backend, DB conn, config)
              so roles stay decoupled from specific wiring.
    NOTES:    Handlers MUST treat this as read-only. Mutating the
              context risks cross-role interference.
    """

    role_name: str
    args: dict[str, Any] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleResult:
    """Handler return shape — uniform for the progress reporter."""

    status: str  # "ok" | "skipped" | "error"
    payload: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class Role:
    """Definition of a runnable role."""

    name: str
    handler: Callable[[RoleContext], RoleResult]
    description: str = ""
    max_concurrency: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class RoleRegistry:
    """In-process catalog of roles + lookup + list helpers.

    PURPOSE:      Replace the "implicit role" anti-pattern from earlier
                  phases with a typed lookup the orchestrator can walk.
    INPUT:        register() from modules that own the role.
    OUTPUT:       resolve() returns the Role or raises KeyError.
    NOTES:        Duplicate registration of the same name replaces the
                  existing role — allows hot-swap in tests.
    """

    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}

    def register(self, role: Role) -> None:
        self._roles[role.name] = role

    def resolve(self, name: str) -> Role:
        try:
            return self._roles[name]
        except KeyError as exc:
            raise KeyError(f"role {name!r} not registered") from exc

    def list(self) -> list[Role]:
        return sorted(self._roles.values(), key=lambda r: r.name)

    def known_names(self) -> list[str]:
        return sorted(self._roles.keys())


def default_registry() -> RoleRegistry:
    """Return a pre-populated registry with the Phase I canonical roles."""
    from .roles import (
        indexer_graph_os,
        lsp_warm_start,
        migrator_embeddings,
    )

    registry = RoleRegistry()
    registry.register(indexer_graph_os.build_role())
    registry.register(lsp_warm_start.build_role())
    registry.register(migrator_embeddings.build_role())
    return registry


__all__ = ["Role", "RoleContext", "RoleResult", "RoleRegistry", "default_registry"]
