"""Regression test: Codex adapter must register every Bash-triggered hook
that Claude registers, where the Codex platform supports the event.

This enforces the SSOT invariant: when a new Phase adds hooks to Claude's
settings.template.json, it must also appear in Codex's hooks.template.json
(or be explicitly marked as Claude-only due to a platform limit like
Write/Edit triggers, which Codex does not support).

Without this test, Codex silently drifts behind Claude — which is what
happened between Phase D and Phase F, where Codex missed six hooks for
multiple releases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

CODING_OS_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_TEMPLATE = CODING_OS_ROOT / "adapters" / "claude" / "settings.template.json"
CODEX_TEMPLATE = CODING_OS_ROOT / "adapters" / "codex" / "hooks.template.json"
CODEX_ADAPTER = CODING_OS_ROOT / "adapters" / "codex" / "adapter.yaml"

# Events Codex supports. Any hook Claude registers under one of these
# events with a Bash-compatible matcher must also appear in Codex.
CODEX_SUPPORTED_EVENTS = {"PreToolUse", "PostToolUse", "Stop", "SessionStart", "UserPromptSubmit"}

# Matchers Codex can trigger. Claude supports "Write|Edit" etc. which
# Codex cannot fire — hooks scoped to those matchers are Claude-only.
CODEX_COMPATIBLE_MATCHERS = {"Bash", ""}

# Explicit whitelist of hooks that are legitimately Claude-only. Add
# with a comment explaining why (usually a platform limit).
CLAUDE_ONLY_WHITELIST: set[str] = {
    # No entries yet — kept as a hook for future Claude-specific
    # features (e.g. Skill tool tracking).
}


def _hook_command(entry: dict) -> str:
    """Return the bare script basename from a hook entry's command field."""
    cmd = entry.get("command", "")
    return cmd.rsplit("/", 1)[-1]


def _collect_hooks_by_event_matcher(template: dict) -> dict[tuple[str, str], set[str]]:
    """Flatten a settings template into {(event, matcher): {hook_script, ...}}."""
    hooks = template.get("hooks", {})
    result: dict[tuple[str, str], set[str]] = {}
    for event, groups in hooks.items():
        for group in groups:
            matcher = group.get("matcher", "")
            key = (event, matcher)
            result.setdefault(key, set())
            for entry in group.get("hooks", []):
                script = _hook_command(entry)
                if script:
                    result[key].add(script)
    return result


def _load_dispatcher_delegate_map() -> dict[tuple[str, str], set[str]]:
    data = yaml.safe_load(CODEX_ADAPTER.read_text(encoding="utf-8")) or {}
    result: dict[tuple[str, str], set[str]] = {}
    for item in data.get("hook_dispatchers") or []:
        key = (str(item["event"]), str(item.get("matcher", "")))
        result.setdefault(key, set()).update(str(d) for d in item.get("delegates") or [])
    return result


def test_codex_covers_all_claude_bash_hooks() -> None:
    """Every Bash-compatible hook Claude registers must appear in Codex."""
    with CLAUDE_TEMPLATE.open() as f:
        claude = json.load(f)
    with CODEX_TEMPLATE.open() as f:
        codex = json.load(f)

    claude_map = _collect_hooks_by_event_matcher(claude)
    codex_map = _collect_hooks_by_event_matcher(codex)
    dispatch_map = _load_dispatcher_delegate_map()

    missing: list[str] = []
    for (event, matcher), scripts in claude_map.items():
        if event not in CODEX_SUPPORTED_EVENTS:
            continue
        if matcher not in CODEX_COMPATIBLE_MATCHERS:
            continue
        codex_scripts = codex_map.get((event, matcher), set())
        for script in scripts:
            if script in CLAUDE_ONLY_WHITELIST:
                continue
            delegated = script in dispatch_map.get((event, matcher), set())
            if script not in codex_scripts and not delegated:
                missing.append(f"{event}/{matcher or '*'}: {script}")

    assert not missing, (
        "Codex hooks.template.json is missing Bash-compatible hooks that "
        "Claude registers. Add them to adapters/codex/hooks.template.json or "
        "whitelist in test_adapter_parity.py::CLAUDE_ONLY_WHITELIST with a "
        "reason.\nMissing:\n  " + "\n  ".join(missing)
    )


def test_no_codex_phantom_hooks() -> None:
    """Every hook file Codex references must exist in core/hooks/ or adapters/codex/hooks/."""
    with CODEX_TEMPLATE.open() as f:
        codex = json.load(f)
    known_hooks = {p.name for p in (CODING_OS_ROOT / "core" / "hooks").glob("*.sh")}
    known_hooks |= {p.name for p in (CODING_OS_ROOT / "adapters" / "codex" / "hooks").glob("*.sh")}
    codex_map = _collect_hooks_by_event_matcher(codex)

    phantom: list[str] = []
    for scripts in codex_map.values():
        for script in scripts:
            if script not in known_hooks:
                phantom.append(script)

    assert not phantom, (
        f"Codex template references hooks that don't exist in core/hooks/ or adapters/codex/hooks/: {phantom}"
    )


@pytest.mark.parametrize("template_path", [CLAUDE_TEMPLATE, CODEX_TEMPLATE])
def test_template_is_valid_json(template_path: Path) -> None:
    """Both templates must be parseable JSON — no trailing commas, etc."""
    with template_path.open() as f:
        data = json.load(f)
    assert "hooks" in data, f"{template_path.name} missing 'hooks' key"
