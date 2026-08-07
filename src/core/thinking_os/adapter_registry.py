from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

logger = logging.getLogger("coding_os.adapter_registry")


def _resolve_adapters_dir(module_path: Path) -> Path:
    # COS_CODING_OS_ROOT wins: a consumer project points at the coding-os
    # checkout that owns src/adapters, which is not a parent of this module.
    configured = os.environ.get("COS_CODING_OS_ROOT", "").strip()
    default = module_path.resolve().parents[2] / "adapters"
    candidates = (
        *((Path(configured).resolve() / "src" / "adapters",) if configured else ()),
        default,
        module_path.resolve().parents[1] / "adapters",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), default)


@dataclass(frozen=True)
class AdapterRecord:
    id: str
    path: Path
    manifest: dict[str, Any]

    @property
    def entrypoints(self) -> dict[str, Any]:
        value = self.manifest.get("runtime_entrypoints")
        return value if isinstance(value, dict) else {}

    @property
    def capabilities(self) -> frozenset[str]:
        values = self.entrypoints.get("capabilities") or []
        return frozenset(str(value) for value in values if value)

    @property
    def models(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            value for value in (self.manifest.get("models") or []) if isinstance(value, dict)
        )

    @property
    def efforts(self) -> tuple[str, ...]:
        return tuple(str(value) for value in (self.manifest.get("efforts") or []) if value)


def load_adapter_records(adapters_dir: Path | None = None) -> dict[str, AdapterRecord]:
    root = adapters_dir or _resolve_adapters_dir(Path(__file__))
    records: dict[str, AdapterRecord] = {}
    if not root.is_dir():
        return records
    for manifest_path in sorted(root.glob("*/adapter.yaml")):
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.debug("adapter manifest skipped %s: %s", manifest_path, exc)
            continue
        if not isinstance(manifest, dict):
            continue
        adapter_id = str(manifest.get("id") or manifest_path.parent.name).strip().lower()
        if not adapter_id or adapter_id != manifest_path.parent.name:
            logger.warning("adapter manifest id/path mismatch: %s", manifest_path)
            continue
        records[adapter_id] = AdapterRecord(adapter_id, manifest_path.parent, manifest)
    return records


def configured_adapter_ids(
    project_root: Path, records: dict[str, AdapterRecord] | None = None
) -> tuple[str, ...]:
    known = records or load_adapter_records()
    config_path = project_root / ".coding-os.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        config = {}
    values = config.get("agents") if isinstance(config, dict) else None
    if not isinstance(values, list):
        return tuple(known)
    return tuple(str(value) for value in values if str(value) in known)


def entrypoint_path(record: AdapterRecord, capability: str) -> Path | None:
    filename = record.entrypoints.get(capability)
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        return None
    path = record.path / filename
    return path if path.is_file() else None


_MODULE_CACHE: dict[tuple[str, str], tuple[float, ModuleType]] = {}


def load_entrypoint_module(record: AdapterRecord, capability: str) -> ModuleType | None:
    path = entrypoint_path(record, capability)
    if path is None:
        return None
    # Executing an adapter entrypoint re-imports its provider SDK, which is far
    # too expensive for a polled Hub route. Keyed on mtime so an edited adapter
    # still reloads rather than serving a stale module.
    key = (record.id, capability)
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = 0.0
    cached = _MODULE_CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    module_name = f"coding_os_adapter_{record.id}_{capability}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.warning("%s %s entrypoint load failed: %s", record.id, capability, exc)
        return None
    _MODULE_CACHE[key] = (stamp, module)
    return module
