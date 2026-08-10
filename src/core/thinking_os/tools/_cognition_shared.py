"""Leaf: the EvidenceBundle on disk and the cognition package accessors.

Imports no cognition sibling, so dispatch and the gate tools can both depend on
it without a cycle — the same shape as _learning_store.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("thinking_os.cognition")

_role_persistence_cache: dict[str, tuple[str | None, Any]] | None = None


def _cog():
    import cognition as _mod

    return _mod


def _schemas():
    import cognition_schemas as _mod

    return _mod


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_role_persistence(role_id: str) -> tuple[str | None, Any]:
    global _role_persistence_cache
    if _role_persistence_cache is None:
        _role_persistence_cache = {}
        cog = _cog()
        schemas_mod = _schemas()
        # Primary source: ROLE_OUTPUT_CLASSES registry in cognition_schemas.
        # Frontmatter `output_schema:` / `bundle_field:` override on a per-
        # role basis (lets a deployment swap the Pydantic class without
        # editing the registry).
        for rid, cls in schemas_mod.ROLE_OUTPUT_CLASSES.items():
            _role_persistence_cache[rid] = (rid, cls)

        try:
            registry = cog.load_agent_registry()
        except Exception as exc:
            logger.warning("agent registry load failed: %s", exc)
            registry = {}
        for rid, meta in registry.items():
            if not isinstance(meta, dict):
                continue
            field = meta.get("bundle_field") or rid
            schema_ref = meta.get("output_schema")
            cls = _role_persistence_cache.get(rid, (None, None))[1]
            if isinstance(schema_ref, str) and schema_ref.strip():
                cls_name = schema_ref.split(".")[-1].strip()
                if cls_name.isidentifier():
                    override = getattr(schemas_mod, cls_name, None)
                    if override is not None:
                        cls = override
            _role_persistence_cache[rid] = (field, cls)
    return _role_persistence_cache.get(role_id, (None, None))


def _all_bundle_fields() -> set[str]:
    """Bundle field names from every registered role (data-driven)."""
    cog = _cog()
    try:
        registry = cog.load_agent_registry()
    except Exception:
        return set()
    out: set[str] = set()
    for rid, meta in registry.items():
        if isinstance(meta, dict):
            out.add(str(meta.get("bundle_field") or rid))
    return out


def _resolve_agent_dir() -> Path:
    import os as _os

    explicit = _os.environ.get("COS_AGENT_DIR")
    if explicit:
        d = Path(explicit)
        d.mkdir(parents=True, exist_ok=True)
        return d
    agent = _os.environ.get("COS_AGENT") or "claude"
    d = Path(".coding-os") / agent
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundle_path(session_id: str) -> Path:
    agent_dir = _resolve_agent_dir()
    return agent_dir / f"evidence_bundle_{session_id}.json"


def _load_bundle(session_id: str, task_marker: str, persona_id: str) -> Any:
    schemas = _schemas()
    path = _bundle_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return schemas.EvidenceBundle.model_validate(data)
        except Exception as exc:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            corrupt = path.with_suffix(f".corrupt-{ts}.json")
            path.rename(corrupt)
            logger.warning("Corrupted bundle quarantined to %s: %s", corrupt, exc)
    return schemas.EvidenceBundle(task_marker=task_marker, persona_id=persona_id)


def _save_bundle(session_id: str, bundle: Any) -> None:
    import fcntl

    path = _bundle_path(session_id)
    payload = bundle.model_dump_json(indent=2)
    # flock-serialize concurrent writers so a parallel run can't interleave a
    # half-written bundle. flush+fsync BEFORE the lock drops — close() releases
    # the lock, and a buffered write would otherwise hit disk after LOCK_UN.
    with path.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        fh.truncate()
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
