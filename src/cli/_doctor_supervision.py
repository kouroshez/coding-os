"""doctor check: agent supervision — is the routing policy reachable and applied?

Private sibling of cli.doctor; the check is re-exported by
`cli.doctor_checks_runtime`.

The gap this closes: `model_routing.enabled` sat true for days while nothing
resolved it per prompt and no check reported on it, so the only way to discover
that supervision was inert was to query the database by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._doctor_shared import (
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)

_CHECK = "supervision.policy_reachable"


def _routing_policy(state: Path) -> dict | None:
    settings = state / "hub-settings.json"
    if not settings.is_file():
        return None
    try:
        raw = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    policy = raw.get("model_routing")
    return policy if isinstance(policy, dict) else None


def _pinned_roles(policy: dict) -> dict[str, str]:
    roles = policy.get("roles")
    if not isinstance(roles, dict):
        return {}
    pinned = {}
    for role, entry in roles.items():
        if isinstance(entry, dict) and entry.get("adapter"):
            pinned[str(role)] = str(entry["adapter"])
    return pinned


def _check_supervision_policy(project: Path, state: Path, report: DoctorReport) -> None:
    """supervision.policy_reachable — routing policy is applied, not merely enabled."""
    policy = _routing_policy(state)
    if policy is None or not policy.get("enabled"):
        report.checks.append(CheckResult(_CHECK, SEV_PASS, "supervision disabled (skip)"))
        return

    mode = str(policy.get("mode") or "explicit")
    threshold = str(policy.get("complexity_threshold") or "COMPLICATED")
    pinned = _pinned_roles(policy)
    summary = f"enabled · mode={mode} · threshold={threshold} · pinned roles={len(pinned)}"

    problems: list[str] = []

    # An enabled policy whose trigger is not installed is the exact failure this
    # check exists for: the nudge announces supervision while nothing applies it.
    hooks_dir = project / "src" / "core" / "hooks"
    if hooks_dir.is_dir() and not (hooks_dir / "resolve-supervise-route.sh").is_file():
        problems.append(
            "resolve-supervise-route.sh missing — policy is announced but never applied"
        )

    # A role pinned to an adapter this project does not have installed can never
    # dispatch; the dispatcher would fail closed at the worst possible moment.
    adapters_dir = project / "src" / "adapters"
    if adapters_dir.is_dir():
        installed = {
            path.name for path in adapters_dir.iterdir() if (path / "adapter.yaml").is_file()
        }
        unknown = sorted(
            f"{role}→{adapter}" for role, adapter in pinned.items() if adapter not in installed
        )
        if unknown:
            problems.append(f"pinned to adapter(s) not installed: {', '.join(unknown)}")

    if problems:
        report.checks.append(CheckResult(_CHECK, SEV_WARN, f"{summary} — {'; '.join(problems)}"))
        return
    report.checks.append(CheckResult(_CHECK, SEV_PASS, summary))
