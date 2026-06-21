"""Discover and load adapter profiles from src/adapters/<id>/adapter.yaml.

An adapter manifest is the single source of truth about what files an
agent produces (.claude/settings.json vs .codex/hooks.json), where its
hooks live, whether it supports path-scoped rules, and what default
settings to deep-merge with aggregated hooks.

Invalid adapter manifests raise hard — unlike stacks, an unparseable
adapter would break `cos init` entirely, so it's better to fail loud.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import yaml

from cli._data_types import AdapterProfile, McpLaunchConfigPath, McpLaunchSpec
from cli._resources import core_dir

try:
    from jsonschema import Draft202012Validator

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    _HAS_JSONSCHEMA = False
    Draft202012Validator = None  # type: ignore

logger = logging.getLogger(__name__)

ADAPTER_MANIFEST_NAME = "adapter.yaml"
SUPPORTED_VERSION = 1

_SCHEMA_DIR = core_dir("schemas")
_ADAPTER_SCHEMA_PATH = _SCHEMA_DIR / "adapter.schema.json"


@lru_cache(maxsize=1)
def _adapter_schema_validator():
    """Lazy-load the adapter.yaml JSON schema validator.

    Returns None if jsonschema is not installed or the schema file is
    missing — handwritten validation below is the fallback.
    """
    if not _HAS_JSONSCHEMA:
        return None
    if not _ADAPTER_SCHEMA_PATH.exists():
        logger.warning("adapter schema not found at %s", _ADAPTER_SCHEMA_PATH)
        return None
    try:
        schema = json.loads(_ADAPTER_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to load adapter schema: %s", exc)
        return None
    return Draft202012Validator(schema)


def _jsonschema_validate_adapter(data: dict, path: Path) -> None:
    """Validate adapter manifest against JSON schema. Raises AdapterManifestError on failure."""
    validator = _adapter_schema_validator()
    if validator is None:
        return
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return
    messages = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        messages.append(f"{loc}: {err.message}")
    joined = "; ".join(messages)
    raise AdapterManifestError(f"{path}: schema validation failed — {joined}")


class AdapterManifestError(ValueError):
    """Raised when an adapter.yaml is structurally invalid."""


def _require(data: dict, key: str, path: Path) -> object:
    if key not in data:
        raise AdapterManifestError(f"{path}: missing required key '{key}'")
    return data[key]


def _load_one(manifest_path: Path) -> AdapterProfile:
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AdapterManifestError(f"{manifest_path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterManifestError(f"{manifest_path}: top level must be a mapping")

    version = data.get("version")
    if version != SUPPORTED_VERSION:
        raise AdapterManifestError(
            f"{manifest_path}: unsupported version {version!r}, expected {SUPPORTED_VERSION}"
        )

    # JSON schema validation — catches malformed fields with precise errors
    # (field path + message). Handwritten checks below stay as a safety net.
    _jsonschema_validate_adapter(data, manifest_path)

    source_dir = manifest_path.parent
    adapter_id = str(_require(data, "id", manifest_path))
    if adapter_id != source_dir.name:
        raise AdapterManifestError(
            f"{manifest_path}: id '{adapter_id}' must match directory '{source_dir.name}'"
        )

    install_script_name = str(data.get("install_script", "install.sh"))
    install_script = source_dir / install_script_name

    sourced_hooks_raw = data.get("sourced_hooks") or []
    if not isinstance(sourced_hooks_raw, list):
        raise AdapterManifestError(f"{manifest_path}: 'sourced_hooks' must be a list")

    default_settings = data.get("default_settings") or {}
    if not isinstance(default_settings, dict):
        raise AdapterManifestError(f"{manifest_path}: 'default_settings' must be a mapping")

    mcp_helper = data.get("mcp_helper")
    if mcp_helper is not None and not isinstance(mcp_helper, str):
        raise AdapterManifestError(f"{manifest_path}: 'mcp_helper' must be a string")

    mcp_launch_raw = data.get("mcp_launch")
    mcp_launch: McpLaunchSpec | None = None
    if mcp_launch_raw is not None:
        if not isinstance(mcp_launch_raw, dict):
            raise AdapterManifestError(f"{manifest_path}: 'mcp_launch' must be a mapping")
        loader = mcp_launch_raw.get("loader")
        if not isinstance(loader, str) or not loader:
            raise AdapterManifestError(
                f"{manifest_path}: 'mcp_launch.loader' must be a non-empty string"
            )
        paths_raw = mcp_launch_raw.get("config_paths") or []
        if not isinstance(paths_raw, list):
            raise AdapterManifestError(f"{manifest_path}: 'mcp_launch.config_paths' must be a list")
        paths: list[McpLaunchConfigPath] = []
        for p in paths_raw:
            if not isinstance(p, dict):
                raise AdapterManifestError(
                    f"{manifest_path}: each 'mcp_launch.config_paths' entry must be a mapping"
                )
            scope = p.get("scope")
            path_val = p.get("path")
            if scope not in ("project", "home"):
                raise AdapterManifestError(
                    f"{manifest_path}: 'mcp_launch.config_paths[].scope' must be 'project' or 'home'"
                )
            if not isinstance(path_val, str) or not path_val:
                raise AdapterManifestError(
                    f"{manifest_path}: 'mcp_launch.config_paths[].path' must be a non-empty string"
                )
            paths.append(McpLaunchConfigPath(scope=scope, path=path_val))
        mcp_launch = McpLaunchSpec(loader=loader, config_paths=tuple(paths))

    runtime_env_markers_raw = data.get("runtime_env_markers") or []
    if not isinstance(runtime_env_markers_raw, list) or not all(
        isinstance(v, str) and v for v in runtime_env_markers_raw
    ):
        raise AdapterManifestError(
            f"{manifest_path}: 'runtime_env_markers' must be a list of non-empty strings"
        )

    return AdapterProfile(
        id=adapter_id,
        label=str(_require(data, "label", manifest_path)),
        settings_file=(str(data["settings_file"]) if data.get("settings_file") else None),
        hooks_dir=str(data["hooks_dir"]) if data.get("hooks_dir") else None,
        rules_dir=str(data["rules_dir"]) if data.get("rules_dir") else None,
        skills_dir=str(data["skills_dir"]) if data.get("skills_dir") else None,
        commands_dir=str(data["commands_dir"]) if data.get("commands_dir") else None,
        sourced_hooks=tuple(str(h) for h in sourced_hooks_raw),
        supports_rules=bool(data.get("supports_rules", False)),
        supports_settings_json=bool(data.get("supports_settings_json", False)),
        install_script=install_script,
        default_settings=dict(default_settings),
        source_dir=source_dir,
        mcp_helper=mcp_helper,
        mcp_launch=mcp_launch,
        runtime_env_markers=tuple(runtime_env_markers_raw),
    )


def _scan_adapter_dir(src: Path, result: dict[str, AdapterProfile], *, fail_hard: bool) -> None:
    for child in sorted(src.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        manifest = child / ADAPTER_MANIFEST_NAME
        if not manifest.exists():
            # Adapters without a manifest are silently skipped — this lets
            # in-progress adapter stubs live in the tree without breaking CLI.
            logger.debug("adapter %s has no %s, skipping", child.name, ADAPTER_MANIFEST_NAME)
            continue
        try:
            profile = _load_one(manifest)
        except (AdapterManifestError, OSError) as exc:
            # OSError too: an unreadable community adapter.yaml must skip in the
            # soft path, never crash the CLI (pass-3 review).
            if fail_hard:
                raise
            logger.warning("skipping community adapter %s: %s", child.name, exc)
            continue
        if profile.id in result:
            if fail_hard:
                raise AdapterManifestError(f"duplicate adapter id '{profile.id}' at {manifest}")
            logger.warning(
                "community adapter id '%s' already loaded (bundled or an earlier overlay) — keeping first",
                profile.id,
            )
            continue
        result[profile.id] = profile


def load_adapter_registry(
    adapters_dir: Path, *, overlay_dirs: tuple[Path, ...] = ()
) -> dict[str, AdapterProfile]:
    """Scan adapters_dir (then out-of-tree overlay_dirs) for */adapter.yaml.

    The bundled dir fails hard on an invalid manifest (a broken core adapter is
    a real error). overlay_dirs hold community adapters ($COS_USER_ADAPTERS_DIR)
    and fail SOFT — a malformed community adapter is skipped, never crashing the
    CLI — and may NOT shadow a bundled adapter id (the bundled one is kept).

    overlay_dirs is OPT-IN (default () = bundled-only); a consumer-discovery call
    site passes the resolved `cli._resources.overlay_adapter_dirs()`. Meta-repo
    SSOT regen + lint stay bundled-only (pass-3 review — defaulting it ON leaked
    community adapters into the regen scripts).
    """
    result: dict[str, AdapterProfile] = {}
    if not adapters_dir.is_dir():
        raise AdapterManifestError(f"adapters dir not found: {adapters_dir}")
    _scan_adapter_dir(adapters_dir, result, fail_hard=True)
    for overlay in overlay_dirs:
        if overlay.is_dir():
            _scan_adapter_dir(overlay, result, fail_hard=False)
    return result
