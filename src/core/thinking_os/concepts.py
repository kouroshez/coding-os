"""
Thinking OS — Concept extraction and spreading activation (TASK-158).

Auto-extract concept tags from file paths and domain context.
1-hop spreading: find patterns sharing 2+ concepts at 0.5x weight.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import PurePosixPath
from typing import Optional

# Path noise: segments that are never meaningful concepts
_PATH_NOISE = {
    # OS / user paths
    "users",
    "home",
    "files",
    "project",
    # Generic structure
    "apps",
    "src",
    "components",
    "utils",
    "lib",
    "tests",
    "test",
    "init",
    "__init__",
    "py",
    "ts",
    "tsx",
    "js",
    "md",
    "json",
    "sh",
    "index",
    "main",
    "base",
    "core",
    "common",
    "shared",
    "app",
    # Config paths
    "claude",
    "hooks",
    "rules",
    "thinking",
    "config",
    "settings",
    "github",
    "workflows",
}

# Maps path keywords → semantic concepts
_COMPONENT_MAP = {
    "models": "model",
    "views": "view",
    "serializers": "serializer",
    "services": "service",
    "selectors": "selector",
    "tasks": "async-task",
    "migrations": "migration",
    "admin": "admin",
    "urls": "routing",
    "signals": "signal",
    "middleware": "middleware",
    "permissions": "auth",
    "management": "cli-command",
}


def _project_relative(file_path: str) -> str:
    """Strip absolute prefix down to project-relative path."""
    from _agent_markers import agent_state_prefixes

    static_markers = ("backend/", "frontend/", ".coding-os/", "docs/", "infrastructure/", "core/")
    markers = static_markers + tuple(agent_state_prefixes())
    lower = file_path.lower()
    for m in markers:
        idx = lower.find(m)
        if idx >= 0:
            return file_path[idx:]
    return PurePosixPath(file_path).name


def extract_concepts(
    *,
    file_path: str = "",
    domain: str = "",
) -> list[str]:
    """Extract semantic concept tags from file path and context.

    Returns 3-7 meaningful tags like ["commerce", "order", "django", "orm"]
    instead of path noise like ["ciro", "claude", "files"].
    """
    concepts: set[str] = set()
    rel = _project_relative(file_path)
    rel_lower = rel.lower()

    # 1. Domain from path structure
    if rel_lower.startswith("backend/"):
        concepts.add("backend")
        # Extract Django app name: backend/apps/<app_name>/...
        parts = PurePosixPath(rel).parts
        for i, p in enumerate(parts):
            if p == "apps" and i + 1 < len(parts):
                concepts.add(parts[i + 1].lower())
                break
    elif rel_lower.startswith("frontend/"):
        concepts.add("frontend")
        # Extract page/feature: frontend/src/app/<feature>/...
        parts = PurePosixPath(rel).parts
        for i, p in enumerate(parts):
            if p in ("app", "components", "lib") and i + 1 < len(parts):
                feature = parts[i + 1].strip("()").lower()
                if feature not in _PATH_NOISE and len(feature) > 2:
                    concepts.add(feature)
                break
    elif rel_lower.startswith("docs/"):
        concepts.add("docs")
    else:
        from _agent_markers import agent_state_prefixes

        infra_prefixes = (".coding-os/", "core/") + tuple(agent_state_prefixes())
        if rel_lower.startswith(infra_prefixes):
            concepts.add("infra")

    # 2. Component type from path keywords
    for keyword, concept in _COMPONENT_MAP.items():
        if f"/{keyword}/" in rel_lower or rel_lower.endswith(f"/{keyword}"):
            concepts.add(concept)

    # 3. File stem — only if meaningful
    stem = PurePosixPath(rel).stem.lower().replace("-", "_")
    if stem not in _PATH_NOISE and len(stem) > 2:
        # Avoid adding generic stems like "commerce" if already captured as app name
        concepts.add(stem)

    # 4. Tech-stack inference
    if "backend/" in rel_lower:
        concepts.add("django")
    if "frontend/" in rel_lower:
        concepts.add("react")
    if "/models/" in rel_lower or rel_lower.endswith("/models.py"):
        concepts.add("orm")
    if "migration" in rel_lower:
        concepts.add("migration")
    if "serializer" in rel_lower:
        concepts.add("api")
    if "test" in rel_lower:
        concepts.add("testing")
    if any(k in rel_lower for k in ("auth", "permission", "login", "token")):
        concepts.add("auth")
    if any(k in rel_lower for k in ("payment", "stripe", "checkout")):
        concepts.add("payments")

    # 5. Explicit domain override
    if domain:
        concepts.add(domain.lower())

    return sorted(concepts)[:7]


def spread_activation(
    conn: sqlite3.Connection,
    *,
    top_result_ids: set[int],
    source_concepts: set[str],
    limit: int = 3,
    min_overlap: int = 2,
) -> list[dict]:
    """1-hop concept expansion: find related patterns sharing 2+ concepts.

    Args:
        conn: SQLite connection.
        top_result_ids: IDs of already-returned results (to exclude).
        source_concepts: Concepts from top results.
        limit: Max spread results.
        min_overlap: Minimum shared concepts.

    Returns:
        List of spread results with 0.5x score modifier.
    """
    if not source_concepts or len(source_concepts) < min_overlap:
        return []

    # Query learned_patterns with concepts that overlap
    rows = conn.execute(
        "SELECT id, pattern, memory_type, domain, confidence, impact_score, "
        "concepts, access_count "
        "FROM learned_patterns "
        "WHERE concepts IS NOT NULL AND confidence > 0.2"
    ).fetchall()

    spread_results: list[dict] = []

    for row in rows:
        d = dict(row)
        if d["id"] in top_result_ids:
            continue

        try:
            pattern_concepts = set(json.loads(d["concepts"]))
        except (json.JSONDecodeError, TypeError):
            continue

        overlap = source_concepts & pattern_concepts
        if len(overlap) < min_overlap:
            continue

        spread_results.append(
            {
                "id": d["id"],
                "title": (d["pattern"] or "")[:60],
                "confidence": d["confidence"],
                "impact_score": d.get("impact_score", 0.5),
                "memory_type": d.get("memory_type", "pattern"),
                "source_table": "learned_patterns",
                "overlap_concepts": sorted(overlap),
                "overlap_count": len(overlap),
                "spread_weight": 0.5,
            }
        )

    # Sort by overlap count * confidence, take top N
    spread_results.sort(
        key=lambda x: x["overlap_count"] * x["confidence"],
        reverse=True,
    )
    return spread_results[:limit]
