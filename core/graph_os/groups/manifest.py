"""Group manifest + membership.yaml handling (I.12)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("graph_os.groups.manifest")


class ConflictError(RuntimeError):
    """Two members declare overlapping `owns` entries."""


@dataclass
class GroupMember:
    alias: str
    path: str  # repo root path
    owned_routes: list[str] = field(default_factory=list)
    owned_mcp_tools: list[str] = field(default_factory=list)
    owned_event_topics: list[str] = field(default_factory=list)

    def owns_route(self, path: str) -> bool:
        return any(_match(path, p) for p in self.owned_routes)

    def owns_event(self, topic: str) -> bool:
        return any(_match(topic, p) for p in self.owned_event_topics)


@dataclass
class GroupManifest:
    name: str
    members: list[GroupMember] = field(default_factory=list)

    def by_alias(self, alias: str) -> GroupMember | None:
        for member in self.members:
            if member.alias == alias:
                return member
        return None

    def validate(self) -> None:
        """Raise ConflictError if two members declare the same route."""
        seen: dict[str, str] = {}
        for member in self.members:
            for route in member.owned_routes:
                existing = seen.get(route)
                if existing and existing != member.alias:
                    raise ConflictError(
                        f"route {route!r} declared by both {existing!r} and {member.alias!r}"
                    )
                seen[route] = member.alias

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "members": [
                {
                    "alias": m.alias,
                    "path": m.path,
                    "owns": {
                        "http_routes": m.owned_routes,
                        "mcp_tools": m.owned_mcp_tools,
                        "event_topics": m.owned_event_topics,
                    },
                }
                for m in self.members
            ],
        }


def load_manifest(path: str | Path) -> GroupManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    members = []
    for entry in data.get("members", []):
        owns = entry.get("owns", {}) or {}
        members.append(
            GroupMember(
                alias=entry["alias"],
                path=entry["path"],
                owned_routes=list(owns.get("http_routes", []) or []),
                owned_mcp_tools=list(owns.get("mcp_tools", []) or []),
                owned_event_topics=list(owns.get("event_topics", []) or []),
            )
        )
    return GroupManifest(name=data["name"], members=members)


def save_manifest(manifest: GroupManifest, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def register_member(
    manifest: GroupManifest,
    *,
    alias: str,
    path: str,
    owned_routes: list[str] | None = None,
    owned_mcp_tools: list[str] | None = None,
    owned_event_topics: list[str] | None = None,
) -> GroupManifest:
    member = GroupMember(
        alias=alias,
        path=path,
        owned_routes=list(owned_routes or []),
        owned_mcp_tools=list(owned_mcp_tools or []),
        owned_event_topics=list(owned_event_topics or []),
    )
    members = [m for m in manifest.members if m.alias != alias]
    members.append(member)
    new_manifest = GroupManifest(name=manifest.name, members=members)
    new_manifest.validate()
    return new_manifest


def _match(path: str, pattern: str) -> bool:
    """Support simple wildcards (`/api/*`, `/internal/**`)."""
    if pattern == path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path.startswith(prefix)
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return path.startswith(prefix) and "/" not in path[len(prefix) + 1:]
    return False


__all__ = [
    "ConflictError",
    "GroupManifest",
    "GroupMember",
    "load_manifest",
    "save_manifest",
    "register_member",
]
