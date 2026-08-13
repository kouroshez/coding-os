"""Compose per-stack `.coding-os/` configs at `cos init`.

Base defaults are deep-merged with each installed stack's overlay, data-driven
(iterates the `templates` list — Rule 11) and multi-stack-correct. Idempotent:
never clobbers an existing target. SSOT: docs/engineering/config-composition.md.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import click
import yaml

# Per-file merge spec: top-level key → strategy. Strategies:
#   "union_by:<key>"  list of dicts, union by <key> (later wins on collision)
#   "union_list"      list of scalars, order-preserving dedupe
#   "dict_merge"      recursive: dicts merge, nested lists union, scalars override
#   "override"        later value wins wholesale
# A key present in an overlay but absent from the spec defaults to "override".
RAG_SPEC: dict[str, str] = {
    "sources": "union_by:path",
    "exclude": "union_list",
    "graph": "dict_merge",
}
SCRUMBAN_SPEC: dict[str, str] = {
    "swimlanes": "union_by:id",
    "wip_limits": "dict_merge",
    "workflow_policy": "dict_merge",
    "label_families": "union_by:name",
}
DOMAIN_SPEC: dict[str, str] = {
    "refs_by_tag": "dict_merge",
    "domain_map": "dict_merge",
    "playbook_map": "dict_merge",
    "default_refs": "override",
    "default_domain": "override",
    "default_playbook": "override",
}

# (filename, spec, format) for each composed config.
_COMPOSED: tuple[tuple[str, dict[str, str], str], ...] = (
    ("rag-config.yaml", RAG_SPEC, "yaml"),
    ("scrumban-config.yaml", SCRUMBAN_SPEC, "yaml"),
    ("domain-config.json", DOMAIN_SPEC, "json"),
)

# Filenames excluded from `_overlay_scaffold` so they don't shadow the composed
# output (first-writer-wins). Kept here as the single source.
COMPOSED_FILENAMES: frozenset[str] = frozenset(name for name, _, _ in _COMPOSED)


def _union_list(base: list[Any], overlay: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for item in [*base, *overlay]:
        marker = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


class _ConflictLog:
    """Same-key/different-value collisions, reported instead of silently
    resolved (config-composition.md § Merge preview + conflict surfacing).
    Later-wins stays the resolution rule — this only makes it visible."""

    def __init__(self) -> None:
        self.entries: list[str] = []
        self.source = "?"

    def record(self, path: str, old: Any, new: Any) -> None:
        old_s, new_s = json.dumps(old, sort_keys=True), json.dumps(new, sort_keys=True)
        self.entries.append(f"{path}: {old_s} → {new_s} (winner: {self.source})")


def _union_by_key(
    base: list[Any], overlay: list[Any], key: str, log: _ConflictLog, path: str
) -> list[Any]:
    out = [copy.deepcopy(item) for item in base]
    index = {item.get(key): i for i, item in enumerate(out) if isinstance(item, dict)}
    for item in overlay:
        if isinstance(item, dict) and item.get(key) in index:
            slot = index[item[key]]
            if out[slot] != item:
                log.record(f"{path}[{item[key]}]", out[slot], item)
            out[slot] = copy.deepcopy(item)  # later wins on collision
        else:
            if isinstance(item, dict):
                index[item.get(key)] = len(out)
            out.append(copy.deepcopy(item))
    return out


def _deep_merge(base: Any, overlay: Any, log: _ConflictLog, path: str) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = copy.deepcopy(base)
        for k, v in overlay.items():
            out[k] = _deep_merge(out[k], v, log, f"{path}.{k}") if k in out else copy.deepcopy(v)
        return out
    if isinstance(base, list) and isinstance(overlay, list):
        return _union_list(base, overlay)
    if base is not None and base != overlay:
        log.record(path, base, overlay)
    return copy.deepcopy(overlay)


def _merge_value(
    base_val: Any, overlay_val: Any, strategy: str, log: _ConflictLog, path: str
) -> Any:
    if overlay_val is None:
        return base_val
    if strategy == "union_list":
        return _union_list(base_val or [], overlay_val or [])
    if strategy == "override":
        if base_val is not None and base_val != overlay_val:
            log.record(path, base_val, overlay_val)
        return copy.deepcopy(overlay_val)
    if strategy == "dict_merge":
        return _deep_merge(base_val or {}, overlay_val, log, path)
    if strategy.startswith("union_by:"):
        return _union_by_key(
            base_val or [], overlay_val or [], strategy.split(":", 1)[1], log, path
        )
    raise ValueError(f"unknown merge strategy: {strategy!r}")


# stack_id becomes a path segment; a traversal here would read a scaffold
# from outside the templates tree.
_STACK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _stack_scaffold_dir(stack_id: str, templates_dir: Path) -> Path:
    """Resolve a stack's scaffold dir — bundled first, then a community overlay
    ($COS_USER_TEMPLATES_DIR, TASK-479). Bundled stacks resolve byte-identically; a
    nonexistent path is returned unchanged so _load() returns None gracefully."""
    if not _STACK_ID_RE.match(stack_id or ""):
        return templates_dir / "__invalid__" / "scaffold"
    bundled = templates_dir / stack_id / "scaffold"
    if bundled.is_dir():
        return bundled
    from cli._resources import overlay_template_dirs

    for root in overlay_template_dirs():
        candidate = root / stack_id / "scaffold"
        if candidate.is_dir():
            return candidate
    return bundled


def compose(
    base: dict[str, Any],
    overlays: list[dict[str, Any]],
    spec: dict[str, str],
    *,
    overlay_names: list[str] | None = None,
    conflicts: list[str] | None = None,
) -> dict[str, Any]:
    """Deep-merge `base` with each overlay in order per the strategy `spec`.

    When `conflicts` is passed, every same-key/different-value collision is
    appended as "<key>[id]: old → new (winner: <overlay_name>)". A stack's
    delta overriding the BASE default is the designed contract, not a
    conflict — only overlay-vs-overlay collisions (second overlay onward)
    are recorded, so a single-stack init never reports any.
    """
    log = _ConflictLog()
    result = copy.deepcopy(base)
    for position, overlay in enumerate(overlays):
        if not isinstance(overlay, dict):
            continue
        log.source = (
            overlay_names[position]
            if overlay_names and position < len(overlay_names)
            else f"overlay[{position}]"
        )
        record_this_pass = conflicts is not None and position > 0
        for key in [*spec, *(k for k in overlay if k not in spec)]:
            if key not in overlay:
                continue
            before = len(log.entries)
            result[key] = _merge_value(
                result.get(key), overlay[key], spec.get(key, "override"), log, key
            )
            if not record_this_pass:
                del log.entries[before:]
    if conflicts is not None:
        conflicts.extend(log.entries)
    return result


def _load(path: Path, fmt: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if fmt == "json" else yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"{path} is not valid {fmt.upper()}: {exc}") from exc
    return data if isinstance(data, dict) else None


_YAML_HEADER = (
    "# GENERATED by `cos init` — composed from base defaults + every installed\n"
    "# stack. Edit freely: init/update never clobbers an existing file. Schema +\n"
    "# merge rules: docs/engineering/config-composition.md\n\n"
)


def _dump(data: dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return _YAML_HEADER + body


def _compose_one(
    filename: str,
    spec: dict[str, str],
    fmt: str,
    templates: list[str],
    templates_dir: Path,
    conflicts: list[str] | None,
) -> dict[str, Any] | None:
    base = _load(templates_dir / "_base" / "scaffold" / ".coding-os" / filename, fmt)
    overlays: list[dict[str, Any]] = []
    overlay_names: list[str] = []
    for stack_id in templates:
        overlay = _load(_stack_scaffold_dir(stack_id, templates_dir) / ".coding-os" / filename, fmt)
        if overlay is not None:
            overlays.append(overlay)
            overlay_names.append(stack_id)
    if base is None and not overlays:
        return None
    file_conflicts: list[str] = []
    merged = compose(
        base or {}, overlays, spec, overlay_names=overlay_names, conflicts=file_conflicts
    )
    if conflicts is not None:
        conflicts.extend(f"{filename}: {entry}" for entry in file_conflicts)
    return merged


def compose_coding_os_configs(
    project: Path,
    state: Path,
    templates: list[str],
    *,
    templates_dir: Path,
    conflicts: list[str] | None = None,
) -> list[str]:
    """Compose `.coding-os/` configs from base + installed stacks. Returns written names."""
    written: list[str] = []
    for filename, spec, fmt in _COMPOSED:
        target = state / filename
        if target.exists():
            continue  # idempotent — never clobber a user / prior-run file
        merged = _compose_one(filename, spec, fmt, templates, templates_dir, conflicts)
        if merged is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump(merged, fmt), encoding="utf-8")
        written.append(filename)
    return written


def preview_coding_os_configs(
    templates: list[str],
    *,
    templates_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Compute the composed configs WITHOUT writing — `cos init --dry-config`.

    Returns ({filename: merged}, conflicts). The wizard's merge-preview source."""
    merged_by_file: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    for filename, spec, fmt in _COMPOSED:
        merged = _compose_one(filename, spec, fmt, templates, templates_dir, conflicts)
        if merged is not None:
            merged_by_file[filename] = merged
    return merged_by_file, conflicts


def recompose_for_added_stack(
    project: Path,
    state: Path,
    stack_id: str,
    *,
    templates_dir: Path,
) -> list[str]:
    """Merge a newly-added stack's `.coding-os/` overlay onto the existing configs.

    Merges onto the CURRENT composed file (not a fresh base) so user edits and
    prior stacks are preserved; re-adding the same stack is a no-op (union
    dedupes). Used by `cos add-stack`. SSOT: docs/engineering/config-composition.md.
    """
    written: list[str] = []
    base_dir = templates_dir / "_base" / "scaffold" / ".coding-os"
    for filename, spec, fmt in _COMPOSED:
        overlay = _load(_stack_scaffold_dir(stack_id, templates_dir) / ".coding-os" / filename, fmt)
        if overlay is None:
            continue
        target = state / filename
        existing = _load(target, fmt)
        base = existing if existing is not None else (_load(base_dir / filename, fmt) or {})
        merged = compose(base, [overlay], spec)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump(merged, fmt), encoding="utf-8")
        written.append(filename)
    return written


def recompose_for_removed_stack(
    project: Path,
    state: Path,
    remaining_templates: list[str],
    *,
    templates_dir: Path,
) -> list[str]:
    """Rebuild the composed `.coding-os/` configs from base + the REMAINING stacks.

    A merged config cannot be un-merged for a single stack (union strategies are
    lossy), so removal recomposes each file fresh from the base defaults plus
    every still-installed stack's overlay — dropping the removed stack's
    contribution. Used by `cos remove-stack`; the caller backs up the targets
    first because this DISCARDS any user edits layered onto the composed files.
    A file is rewritten only when the recompose differs from the current target,
    so the operation is diff-minimal and idempotent. SSOT:
    docs/engineering/config-composition.md.
    """
    written: list[str] = []
    base_dir = templates_dir / "_base" / "scaffold" / ".coding-os"
    for filename, spec, fmt in _COMPOSED:
        target = state / filename
        if not target.is_file():
            continue  # nothing composed here — nothing to rebuild
        base = _load(base_dir / filename, fmt)
        overlays: list[dict[str, Any]] = []
        for stack_id in remaining_templates:
            overlay = _load(
                _stack_scaffold_dir(stack_id, templates_dir) / ".coding-os" / filename, fmt
            )
            if overlay is not None:
                overlays.append(overlay)
        merged = compose(base or {}, overlays, spec)
        new_text = _dump(merged, fmt)
        if target.read_text(encoding="utf-8") == new_text:
            continue  # recompose is a no-op for this file
        target.write_text(new_text, encoding="utf-8")
        written.append(filename)
    return written
