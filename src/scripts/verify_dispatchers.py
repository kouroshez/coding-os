#!/usr/bin/env python3
"""
Coding OS — verify that adapter dispatcher delegate lists track registry.yaml.

PURPOSE:
    The Codex adapter installs shim scripts (codex-*-dispatch.sh) that
    internally fan out to a HARDCODED list of core
    hook scripts. When a hook is added to core/hooks/registry.yaml for one
    of those events (SessionStart, UserPromptSubmit, etc.), the registry
    edit alone does not reach those adapters — the dispatcher's delegate
    list must also be updated.

    This script reports any registry hook that should fire for an adapter
    (per its `hook_capabilities`) but is missing from the corresponding
    dispatcher's hardcoded list. Exits 1 on drift, 0 on clean.

USAGE:
    python3 scripts/verify_dispatchers.py
    make verify-dispatchers          # registered as a Makefile target

NOTES:
    Codex's dispatcher pattern is intentional (hardcoded delegate list).
    The user has decided NOT to auto-generate that list. This script is the
    drift-detection layer that catches forgetfulness without changing the
    dispatch design.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src"
REGISTRY = SRC_ROOT / "core" / "hooks" / "registry.yaml"

# The rendered settings/hooks file we compare against, keyed by adapter.
RENDERED_TEMPLATE: dict[str, Path] = {
    "claude": SRC_ROOT / "adapters" / "claude" / "settings.template.json",
    "codex": SRC_ROOT / "adapters" / "codex" / "hooks.template.json",
}

# Map: (adapter, event, matcher) -> dispatcher script path. The matcher
# field disambiguates so a hook whose matcher is `Bash` isn't flagged
# "missing" from a sibling dispatcher with a different matcher.
DISPATCHERS: dict[tuple[str, str, str], Path] = {
    ("codex", "SessionStart", "startup"): SRC_ROOT
    / "adapters"
    / "codex"
    / "hooks"
    / "codex-sessionstart-dispatch.sh",
    ("codex", "PreToolUse", "Bash"): SRC_ROOT
    / "adapters"
    / "codex"
    / "hooks"
    / "codex-pretool-dispatch.sh",
    ("codex", "PostToolUse", "Bash"): SRC_ROOT
    / "adapters"
    / "codex"
    / "hooks"
    / "codex-posttool-dispatch.sh",
    ("codex", "Stop", ""): SRC_ROOT / "adapters" / "codex" / "hooks" / "codex-stop-dispatch.sh",
    ("codex", "UserPromptSubmit", ""): SRC_ROOT
    / "adapters"
    / "codex"
    / "hooks"
    / "codex-userpromptsubmit-dispatch.sh",
}

# Hooks the dispatcher cannot meaningfully delegate (their I/O contract is
# specific to the adapter; or they're internal to the dispatcher pattern itself).
DISPATCHER_INTERNAL = {
    # The dispatcher script names themselves — never expected to delegate to themselves.
    "codex-sessionstart-dispatch",
    "codex-pretool-dispatch",
    "codex-posttool-dispatch",
    "codex-stop-dispatch",
    "codex-userpromptsubmit-dispatch",
}


def load_registry() -> list[dict]:
    return (yaml.safe_load(REGISTRY.read_text())["hooks"]) or []


def parse_delegate_list(script: Path) -> set[str]:
    """Extract hook names from `for delegate in <list>; do` block.

    The dispatcher uses bash multi-line continuation:
        for delegate in \
          block-secrets.sh \
          block-dangerous-commands.sh \
          ...; do
    so we strip backslashes + newlines before splitting on whitespace.
    """
    text = script.read_text()
    m = re.search(
        r"for\s+delegate\s+in\s+(.*?);\s*do",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        return set()
    body = m.group(1)
    # Drop line-continuation backslashes and collapse whitespace.
    body = body.replace("\\\n", " ").replace("\\", " ")
    parts = body.split()
    # Strip .sh suffix to compare with registry IDs; ignore empty tokens.
    return {(p[:-3] if p.endswith(".sh") else p) for p in parts if p and p != "\\"}


def adapter_hook_capabilities(adapter: str) -> dict[str, list[str]]:
    p = SRC_ROOT / "adapters" / adapter / "adapter.yaml"
    data = yaml.safe_load(p.read_text())
    caps: dict[str, list[str]] = {}
    for ev, body in (data.get("hook_capabilities") or {}).items():
        caps[ev] = body.get("matchers") or []
    return caps


def rendered_direct_hooks(adapter: str, event: str) -> set[str]:
    """Hooks listed DIRECTLY (not via a dispatcher) in the rendered template
    for this (adapter, event) pair.

    Codex splits hooks: some are inline in the rendered template
    (e.g. PostToolUse:Skill → track-skill.sh fires directly), others are
    delegated to a dispatcher script that fans out to a hardcoded list. This
    function pulls the inline ones so the drift check considers them already
    covered.
    """
    template = RENDERED_TEMPLATE.get(adapter)
    if template is None or not template.exists():
        return set()
    try:
        data = json.loads(template.read_text())
    except (OSError, json.JSONDecodeError):
        return set()

    inline: set[str] = set()
    blocks = data.get("hooks", {}).get(event, []) or []
    for block in blocks:
        for entry in block.get("hooks") or []:
            cmd = entry.get("command") or ""
            # Strip the {{HOOKS_DIR}}/ template var and trailing .sh.
            stem = cmd.rsplit("/", 1)[-1]
            if stem.endswith(".sh"):
                stem = stem[:-3]
            # Dispatcher scripts are themselves entries in the rendered
            # template; we want to ignore them (they're checked separately
            # via parse_delegate_list).
            if stem in DISPATCHER_INTERNAL:
                continue
            if stem:
                inline.add(stem)
    return inline


def expected_delegates(
    adapter: str,
    event: str,
    matcher: str,
    registry: list[dict],
) -> set[str]:
    """Hooks that SHOULD be reachable from the dispatcher (or inline) for the
    (adapter, event, matcher) triple.

    Filter: registry entry declares this exact `event` AND its matcher equals
    `matcher` (so codex-pretool-dispatch.sh — Bash only — doesn't get blamed
    for missing Write|Edit hooks that belong to a sibling Write|Edit dispatcher).
    Adapter capabilities are still respected: if the adapter can't fire that
    matcher, the hook is excluded.
    """
    caps = adapter_hook_capabilities(adapter)
    if matcher not in (caps.get(event) or []):
        return set()
    expected: set[str] = set()
    for h in registry:
        for ev in h.get("events", []):
            if ev.get("event") != event:
                continue
            if (ev.get("matcher") or "") != matcher:
                continue
            expected.add(h["id"])
    return expected


def main() -> int:
    registry = load_registry()
    drift_found = False

    for (adapter, event, matcher), script in DISPATCHERS.items():
        label = f"{adapter}/{event}:{matcher or '∅'}"
        if not script.exists():
            print(f"  ⚠ {label}: dispatcher script missing ({script.name})")
            continue
        delegated = parse_delegate_list(script) - DISPATCHER_INTERNAL
        inline = rendered_direct_hooks(adapter, event)
        # A hook is "covered" if it's reached either way (delegated or inline).
        actual = delegated | inline
        expected = expected_delegates(adapter, event, matcher, registry) - DISPATCHER_INTERNAL
        missing = expected - actual
        # `unexpected` flags ONLY hooks delegated by THIS dispatcher whose
        # registry matcher doesn't fit. Hooks that fit a SIBLING dispatcher
        # (e.g. block-secrets is in pretool-dispatch.sh which is Bash, but
        # also delegated by pretool-write-dispatch.sh which is Write|Edit)
        # are not surprising — they're defensive double-coverage.
        sibling_matchers = {m for (a, e, m) in DISPATCHERS if a == adapter and e == event}
        sibling_expected: set[str] = set()
        for sm in sibling_matchers:
            sibling_expected |= expected_delegates(adapter, event, sm, registry)
        unexpected = (delegated - expected) - sibling_expected - DISPATCHER_INTERNAL

        if not missing and not unexpected:
            print(
                f"  ✓ {label}: "
                f"{len(delegated)} delegated + {len(inline)} inline = {len(actual)} aligned"
            )
            continue
        drift_found = True
        print(f"  ✗ {label} ({script.name}):")
        if missing:
            print(f"      missing (neither delegated nor inline): {sorted(missing)}")
            print("      → add to the dispatcher's `for delegate in ...; do` list")
        if unexpected:
            print(
                f"      unexpected delegate (not in any sibling registry entry): {sorted(unexpected)}"
            )
            print("      → remove from dispatcher OR add to registry")

    if drift_found:
        print()
        print("DRIFT DETECTED — adapter dispatchers are out of sync with registry.yaml.")
        print("Fix the dispatcher scripts above, then re-run `make verify-dispatchers`.")
        return 1
    print()
    print("All adapter dispatchers aligned with registry.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
