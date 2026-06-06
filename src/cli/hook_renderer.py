"""Render hook registrations from src/core/hooks/registry.yaml into
adapter-specific settings files.

SSOT flow:
    src/core/hooks/registry.yaml
        ↓  load_registry()
    list[HookEntry]
        ↓  render_for_adapter(caps)
    {hooks: {PreToolUse: [...], ...}}   ← adapter-specific, event/matcher-filtered
        ↓  write as JSON
    src/adapters/<agent>/settings.template.json  (or hooks.template.json)

Each adapter's install.sh still substitutes `{{HOOKS_DIR}}` at install
time — the rendered file is checked into the repo as a snapshot so
diffs stay visible and existing tests/golden fixtures keep working.

Usage (Python):
    from cli.hook_renderer import render_all
    render_all()

Usage (CLI, via `make regen-adapter-templates`):
    python -m cli.hook_renderer
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HOOKS_DIR_PLACEHOLDER = "{{HOOKS_DIR}}"

# Hook execution order within a single (event, matcher) group is contractual,
# not incidental: hard safety checks (credential / dangerous-command scans)
# MUST run before slower enforcement gates so a block is reached early and the
# user sees the most critical reason first. The renderer sorts every group by
# this category precedence, breaking ties by registry declaration index (a
# stable sort) so order stays deterministic as hooks are appended. New
# categories default to the tail. Dispatcher-coalesced groups (Codex) are
# replaced wholesale afterwards and keep their own delegate order.
# Contract: docs/engineering/adapter-parity.md § Execution order within a group.
CATEGORY_PRECEDENCE: dict[str, int] = {
    "safety": 0,
    "enforcement": 10,
    "cognition": 20,
    "task": 25,
    "retrieval": 30,
    "observability": 40,
    "reminder": 50,
    "meta": 60,
}
_CATEGORY_PRECEDENCE_TAIL = 99


@dataclass(frozen=True)
class HookEntry:
    """One hook declaration from registry.yaml.

    `adapter_scope` (added 2026-05-05):
        - None / empty → cross-adapter; renderer keeps for every adapter
          whose hook_capabilities allow the event/matcher pair.
        - A specific adapter id (e.g. an entry from adapters/) → renderer ONLY emits
          this hook for that adapter. The script must live under
          src/adapters/<adapter>/hooks/ (resolved by the installer's
          two-pass symlink so .claude/hooks/<script> ends up pointing
          at the adapter-private file).
    """

    id: str
    script: str
    description: str
    category: str
    phase: str
    events: list[dict[str, Any]]
    timeout: int | None = None
    adapter_scope: str | None = None


@dataclass(frozen=True)
class AdapterCapabilities:
    """Event/matcher pairs an adapter can actually fire."""

    agent_id: str
    # {event_name: [matcher1, matcher2, ...]}
    by_event: dict[str, list[str]] = field(default_factory=dict)
    dispatchers: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def _flatten_matchers(self, event: str) -> list[str]:
        """Return the ordered atomic matcher tokens supported for an event."""
        flattened: OrderedDict[str, None] = OrderedDict()
        for matcher in self.by_event.get(event, []):
            if matcher == "":
                flattened[""] = None
                continue
            for token in matcher.split("|"):
                token = token.strip()
                if token:
                    flattened[token] = None
        return list(flattened.keys())

    def resolve_matcher(self, event: str, matcher: str) -> str | None:
        """Return the adapter-safe matcher to render, or None if unsupported.

        Registry matchers can be broader than an adapter's runtime support.
        Example: registry may declare `compact|resume`, while current Codex
        only supports `resume`. In that case we keep the supported subset.
        """
        supported_tokens = self._flatten_matchers(event)
        if not supported_tokens and matcher != "":
            return None
        if matcher == "":
            return "" if "" in supported_tokens else None

        requested = [token.strip() for token in matcher.split("|") if token.strip()]
        kept = [token for token in requested if token in supported_tokens]
        if not kept:
            return None
        if kept == requested:
            return matcher
        return "|".join(kept)

    def supports(self, event: str, matcher: str) -> bool:
        return self.resolve_matcher(event, matcher) is not None


def load_registry(registry_path: Path) -> list[HookEntry]:
    """Parse registry.yaml into HookEntry objects. Strict on malformed data."""
    if not registry_path.exists():
        raise FileNotFoundError(f"hook registry missing: {registry_path}")
    with registry_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries: list[HookEntry] = []
    for item in data.get("hooks", []) or []:
        hook_id = item.get("id")
        script = item.get("script")
        if not hook_id or not script:
            raise ValueError(f"hook entry missing id/script: {item!r}")
        scope_raw = item.get("adapter_scope")
        adapter_scope = str(scope_raw).strip() if scope_raw else None
        entries.append(
            HookEntry(
                id=hook_id,
                script=script,
                description=item.get("description", ""),
                category=item.get("category", "uncategorized"),
                phase=str(item.get("phase", "")),
                events=list(item.get("events") or []),
                timeout=item.get("timeout"),
                adapter_scope=adapter_scope,
            )
        )
    return entries


def load_adapter_capabilities(adapter_yaml: Path) -> AdapterCapabilities:
    """Read the hook_capabilities section from src/adapters/<id>/adapter.yaml."""
    with adapter_yaml.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    caps_raw = data.get("hook_capabilities") or {}
    by_event: dict[str, list[str]] = {}
    for event, entry in caps_raw.items():
        matchers = (entry or {}).get("matchers") or [""]
        by_event[event] = list(matchers)
    dispatchers: dict[tuple[str, str], dict[str, Any]] = {}
    for item in data.get("hook_dispatchers") or []:
        event = str(item["event"])
        matcher = str(item.get("matcher", ""))
        dispatchers[(event, matcher)] = {
            "script": str(item["script"]),
            "status_message": str(item.get("status_message", "")),
            "timeout": item.get("timeout"),
            "delegates": list(item.get("delegates") or []),
        }
    return AdapterCapabilities(
        agent_id=str(data.get("id", "")),
        by_event=by_event,
        dispatchers=dispatchers,
    )


def render_for_adapter(registry: list[HookEntry], caps: AdapterCapabilities) -> dict[str, Any]:
    """Walk the registry once, keep only events this adapter can fire.

    Output shape matches both Claude's settings.template.json and Codex's
    hooks.template.json — both use the same {"hooks": {event: [{matcher, hooks: [...]}]}}
    structure.
    """
    output: dict[str, Any] = {"hooks": {}}
    for idx, hook in enumerate(registry):
        # Adapter-scope filter: an entry tagged with a
        # specific adapter only renders for that adapter. Untagged
        # entries remain cross-adapter.
        if hook.adapter_scope and hook.adapter_scope != caps.agent_id:
            continue
        sort_key = (
            CATEGORY_PRECEDENCE.get(hook.category, _CATEGORY_PRECEDENCE_TAIL),
            idx,
        )
        for ev in hook.events:
            event = ev["event"]
            matcher = ev.get("matcher", "")
            rendered_matcher = caps.resolve_matcher(event, matcher)
            if rendered_matcher is None:
                continue

            groups = output["hooks"].setdefault(event, [])
            group = next(
                (g for g in groups if g.get("matcher", "") == rendered_matcher),
                None,
            )
            if group is None:
                group = {"matcher": rendered_matcher, "hooks": []}
                groups.append(group)

            entry: dict[str, Any] = {
                "type": "command",
                "command": f"{HOOKS_DIR_PLACEHOLDER}/{hook.script}",
            }
            if ev.get("status_message"):
                entry["statusMessage"] = ev["status_message"]
            if hook.timeout:
                entry["timeout"] = hook.timeout
            entry["_sort"] = sort_key
            group["hooks"].append(entry)

    # Deterministic ordering: sort every group by category precedence (stable
    # tie-break on registry index) BEFORE dispatcher coalescing replaces a
    # group wholesale. Strip the temporary sort key from the emitted entries.
    for groups in output["hooks"].values():
        for group in groups:
            group["hooks"].sort(key=lambda e: e["_sort"])
            for e in group["hooks"]:
                del e["_sort"]

    for (event, matcher), dispatcher in caps.dispatchers.items():
        groups = output["hooks"].setdefault(event, [])
        group = next((g for g in groups if g.get("matcher", "") == matcher), None)
        if group is None:
            group = {"matcher": matcher, "hooks": []}
            groups.append(group)
        entry: dict[str, Any] = {
            "type": "command",
            "command": f"{HOOKS_DIR_PLACEHOLDER}/{dispatcher['script']}",
        }
        if dispatcher.get("status_message"):
            entry["statusMessage"] = dispatcher["status_message"]
        timeout = dispatcher.get("timeout")
        if timeout:
            entry["timeout"] = timeout
        group["hooks"] = [entry]
    return output


def render_all(
    *,
    registry_path: Path | None = None,
    adapters_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Path]:
    """Render the registry for every adapter and write the template files.

    Returns a {agent_id: output_path} map. With dry_run=True, returns the
    same map but no files are written.
    """
    root = Path(__file__).resolve().parent.parent.parent
    registry_path = registry_path or root / "src" / "core" / "hooks" / "registry.yaml"
    adapters_dir = adapters_dir or root / "src" / "adapters"

    registry = load_registry(registry_path)
    written: dict[str, Path] = {}

    for adapter_yaml in sorted(adapters_dir.glob("*/adapter.yaml")):
        caps = load_adapter_capabilities(adapter_yaml)
        if not caps.by_event:
            continue  # adapter did not declare capabilities yet

        with adapter_yaml.open(encoding="utf-8") as f:
            adapter_data = yaml.safe_load(f) or {}
        target_name = adapter_data.get("hook_registry_output")
        if not target_name:
            continue  # adapter does not consume the hook registry

        rendered = render_for_adapter(registry, caps)
        target = adapter_yaml.parent / target_name

        if not dry_run:
            target.write_text(
                json.dumps(rendered, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        written[caps.agent_id] = target

    return written


def list_hooks_for_agent(
    registry: list[HookEntry], agent: str, adapters_dir: Path
) -> list[HookEntry]:
    """Filter registry to hooks at least one of whose events the agent can fire."""
    adapter_yaml = adapters_dir / agent / "adapter.yaml"
    if not adapter_yaml.exists():
        raise FileNotFoundError(f"adapter not found: {agent}")
    caps = load_adapter_capabilities(adapter_yaml)
    return [
        h
        for h in registry
        if any(caps.supports(e["event"], e.get("matcher", "")) for e in h.events)
    ]


def _main() -> None:
    """Entry point for `python -m cli.hook_renderer` (wired into Makefile)."""
    written = render_all()
    for agent_id, path in sorted(written.items()):
        print(f"[hook-renderer] {agent_id:8s} → {path.relative_to(Path.cwd())}", file=sys.stderr)


if __name__ == "__main__":
    _main()
