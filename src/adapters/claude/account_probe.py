"""Claude account state — plan, auth mode and rate-limit windows.

Claude Code caches what its `/usage` view shows into `~/.claude.json` under
`cachedUsageUtilization`. Reading that cache is the whole implementation: there
is no local API to call, and the OAuth token that would reach the remote one is
deliberately out of scope — a quota panel is not worth handling a credential.

Only percentages, reset times and plan tier leave this module. The same file
holds the account email, org name and several uuids; none of them are part of
the contract and none are returned.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thinking_os.account_status import unavailable

SOURCE = "~/.claude.json :: cachedUsageUtilization"

# Claude Code publishes each window twice: once named (`five_hour`, `seven_day`)
# and once in `limits[]` keyed by group. The named pair carries the durations,
# the array carries severity and per-model scope, and both agree on resets_at —
# which is what licenses reading the durations off one and the rows off the other.
_GROUP_MINUTES = {"session": 300, "weekly": 10080}

_KIND_LABELS = {
    "session": "5h",
    "weekly_all": "weekly",
    "weekly_scoped": "weekly",
}


def _config_path() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / ".claude.json"
    return Path.home() / ".claude.json"


def _auth_mode(raw: dict[str, Any]) -> str:
    # An API key in the environment wins over the plan: the SDK bills it, so the
    # subscription the account also holds is not what this dispatch spends.
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "api_key"
    account = raw.get("oauthAccount")
    billing = str(account.get("billingType") or "") if isinstance(account, dict) else ""
    return "subscription" if "subscription" in billing else "unknown"


def _plan(raw: dict[str, Any]) -> str:
    account = raw.get("oauthAccount")
    if not isinstance(account, dict):
        return ""
    kind = str(account.get("organizationType") or "").strip()
    tier = str(account.get("organizationRateLimitTier") or "").strip()
    if kind and tier and tier != kind:
        return f"{kind} ({tier})"
    return kind or tier


def _scope_label(entry: dict[str, Any]) -> str | None:
    scope = entry.get("scope")
    if not isinstance(scope, dict):
        return None
    model = scope.get("model")
    if isinstance(model, dict):
        name = str(model.get("display_name") or model.get("id") or "").strip()
        if name:
            return name
    surface = scope.get("surface")
    return str(surface).strip() or None if surface else None


def _from_limits(limits: Any) -> list[dict[str, Any]]:
    windows = []
    for entry in limits if isinstance(limits, list) else []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        scope = _scope_label(entry)
        label = _KIND_LABELS.get(kind, kind or "window")
        windows.append(
            {
                "label": f"{label} · {scope}" if scope else label,
                "percent": entry.get("percent"),
                "resets_at": entry.get("resets_at"),
                "severity": entry.get("severity"),
                "window_minutes": _GROUP_MINUTES.get(str(entry.get("group") or "")),
                "scope": scope,
            }
        )
    return windows


def _from_named(utilization: dict[str, Any]) -> list[dict[str, Any]]:
    # Fallback for a Claude Code that has not published `limits[]` yet. It loses
    # severity and per-model scope, which is why it is second choice, not first.
    named = (("five_hour", "5h", 300), ("seven_day", "weekly", 10080))
    windows = []
    for key, label, minutes in named:
        entry = utilization.get(key)
        if not isinstance(entry, dict):
            continue
        windows.append(
            {
                "label": label,
                "percent": entry.get("utilization"),
                "resets_at": entry.get("resets_at"),
                "window_minutes": minutes,
            }
        )
    return windows


def probe_account() -> dict[str, Any]:
    """Report Claude plan, auth mode and rate-limit windows from the local cache."""
    path = _config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return unavailable("claude", f"{path.name} unreadable: {type(exc).__name__}", SOURCE)
    if not isinstance(raw, dict):
        return unavailable("claude", f"{path.name} is not a JSON object", SOURCE)

    cached = raw.get("cachedUsageUtilization")
    if not isinstance(cached, dict):
        return unavailable(
            "claude",
            "no cached usage yet — open Claude Code and run /usage once",
            SOURCE,
        )
    utilization = cached.get("utilization")
    utilization = utilization if isinstance(utilization, dict) else {}
    windows = _from_limits(utilization.get("limits")) or _from_named(utilization)

    fetched_ms = cached.get("fetchedAtMs")
    observed_at = None
    if isinstance(fetched_ms, (int, float)) and fetched_ms > 0:
        observed_at = datetime.fromtimestamp(fetched_ms / 1000, tz=timezone.utc).isoformat()

    return {
        "status": "ok" if windows else "unavailable",
        "reason": "" if windows else "cached usage carries no windows",
        "auth_mode": _auth_mode(raw),
        "plan": _plan(raw),
        "source": SOURCE,
        "observed_at": observed_at,
        "windows": windows,
    }
