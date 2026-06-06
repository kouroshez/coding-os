"""PreToolUse fan-out budget guard (TASK-196, observability-eye B2).

Every PreToolUse Bash command pays the cost of EVERY hook registered on that
{event, matcher} pair. Without a ceiling the hook layer drifts toward
death-by-a-thousand-hooks: each new gate adds latency to every Bash call the
agent makes. This test caps the fan-out so a registry edit that pushes past
the budget fails CI instead of silently taxing every tool call.

Budget is on the Bash pair specifically — it fires on every shell command the
agent runs, so it is the hot path the audit (observability-eye B2) guards. The
Write|Edit pair is a larger, deliberate population of enforcement gates that
only fire on a file write (not on every command), so it carries its own,
higher ceiling rather than the Bash budget.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

_REGISTRY = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "registry.yaml"

# Headroom over the current count (8 PreToolUse Bash hooks).
# Raising this is a deliberate decision — bump it AND justify the new latency
# budget in docs/engineering/observability-eye.md, never as a drive-by.
PRETOOLUSE_BASH_BUDGET = 12

# Write|Edit only fires on a file write, not on every command, and already
# carries a deliberate population of enforcement gates (23).
# Its ceiling guards against unbounded growth, not against per-command latency.
PRETOOLUSE_WRITE_EDIT_BUDGET = 28


def _pretooluse_fanout() -> Counter[str]:
    registry = yaml.safe_load(_REGISTRY.read_text())
    fanout: Counter[str] = Counter()
    for hook in registry["hooks"]:
        for event in hook.get("events", []):
            if event.get("event") != "PreToolUse":
                continue
            matcher = event.get("matcher", "") or "(empty)"
            fanout[matcher] += 1
    return fanout


def test_registry_parses() -> None:
    fanout = _pretooluse_fanout()
    assert fanout, "expected at least one PreToolUse hook in the registry"


def test_pretooluse_bash_fanout_within_budget() -> None:
    bash = _pretooluse_fanout().get("Bash", 0)
    assert bash <= PRETOOLUSE_BASH_BUDGET, (
        f"PreToolUse Bash fan-out is {bash}, over budget {PRETOOLUSE_BASH_BUDGET}. "
        "Each Bash command now pays for one more hook. Merge into an existing gate "
        "or raise the budget deliberately in observability-eye.md."
    )


def test_pretooluse_write_edit_fanout_within_budget() -> None:
    write_edit = _pretooluse_fanout().get("Write|Edit", 0)
    assert write_edit <= PRETOOLUSE_WRITE_EDIT_BUDGET, (
        f"PreToolUse Write|Edit fan-out is {write_edit}, over ceiling "
        f"{PRETOOLUSE_WRITE_EDIT_BUDGET}. Merge into an existing gate or raise the "
        "ceiling deliberately in observability-eye.md."
    )
