"""Provider account state — plan, auth mode, and the rate-limit windows in force.

Answers the question a cost figure cannot: *how much of the plan is left*. On a
subscription the dollar number is notional, so remaining quota is the only
budget the operator actually spends against.

Each adapter owns the reading (`runtime_entrypoints.account`, capability
`account`) because only it knows where its runtime caches that state; this
module owns the shape, the aggregation, and the refusal to invent a number.
Contract: docs/engineering/agent-supervision.md.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thinking_os.adapter_registry import (
    AdapterRecord,
    configured_adapter_ids,
    load_adapter_records,
    load_entrypoint_module,
)

logger = logging.getLogger("coding_os.account_status")

ACCOUNT_CAPABILITY = "account"
PROBE_ATTRIBUTE = "probe_account"

# Both providers publish a percentage, not a countdown, and the shortest window
# either meters is five hours — 3.3 points per ten minutes at a steady burn. A
# reading older than this can therefore be wrong by more than five points, which
# is enough to turn "room to spare" into "about to be cut off".
STALE_AFTER_SECONDS = 900

_SEVERITIES = ("normal", "warning", "critical")


@dataclass(frozen=True)
class QuotaWindow:
    label: str
    percent: float
    resets_at: str | None = None
    severity: str = "normal"
    window_minutes: int | None = None
    scope: str | None = None


@dataclass(frozen=True)
class AccountReport:
    adapter: str
    status: str = "unavailable"
    reason: str = ""
    auth_mode: str = "unknown"
    plan: str = ""
    source: str = ""
    observed_at: str | None = None
    age_seconds: int | None = None
    stale: bool = False
    windows: list[QuotaWindow] = field(default_factory=list)


def window_label(minutes: int | None) -> str:
    if not minutes or minutes <= 0:
        return "window"
    if minutes % 10080 == 0:
        weeks = minutes // 10080
        return "weekly" if weeks == 1 else f"{weeks}-weekly"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "daily" if days == 1 else f"{days}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def age_of(observed_at: str | None, now: datetime | None = None) -> int | None:
    if not observed_at:
        return None
    try:
        stamp = datetime.fromisoformat(observed_at)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    clock = now or datetime.now(timezone.utc)
    return max(0, int((clock - stamp).total_seconds()))


def unavailable(adapter: str, reason: str, source: str = "") -> dict[str, Any]:
    """Build the one shape a probe may return when it has no numbers to report."""
    return asdict(AccountReport(adapter=adapter, reason=reason, source=source))


def _coerce_percent(value: Any) -> float | None:
    # A window without a real percentage is dropped rather than shown as 0: a
    # zero reads as "nothing used", which is the opposite of "not known".
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return round(float(value), 1)


def _coerce_window(raw: Any) -> QuotaWindow | None:
    if not isinstance(raw, dict):
        return None
    percent = _coerce_percent(raw.get("percent"))
    if percent is None:
        return None
    minutes = raw.get("window_minutes")
    minutes = int(minutes) if isinstance(minutes, (int, float)) and minutes > 0 else None
    severity = str(raw.get("severity") or "normal").lower()
    label = str(raw.get("label") or "").strip() or window_label(minutes)
    resets_at = raw.get("resets_at")
    scope = raw.get("scope")
    return QuotaWindow(
        label=label,
        percent=percent,
        resets_at=str(resets_at) if resets_at else None,
        severity=severity if severity in _SEVERITIES else "normal",
        window_minutes=minutes,
        scope=str(scope) if scope else None,
    )


def normalize_report(adapter: str, raw: Any, now: datetime | None = None) -> dict[str, Any]:
    """Coerce whatever a probe returned into the reporting shape, or unavailable."""
    if not isinstance(raw, dict):
        return unavailable(adapter, "probe returned no mapping")
    reason = str(raw.get("reason") or "")
    source = str(raw.get("source") or "")
    windows = [w for w in (_coerce_window(item) for item in raw.get("windows") or []) if w]
    if str(raw.get("status") or "") != "ok" or not windows:
        return unavailable(adapter, reason or "no rate-limit windows reported", source)
    observed_at = raw.get("observed_at")
    observed_at = str(observed_at) if observed_at else None
    age = age_of(observed_at, now)
    report = AccountReport(
        adapter=adapter,
        status="ok",
        auth_mode=str(raw.get("auth_mode") or "unknown"),
        plan=str(raw.get("plan") or ""),
        source=source,
        observed_at=observed_at,
        age_seconds=age,
        stale=age is not None and age > STALE_AFTER_SECONDS,
        windows=sorted(windows, key=lambda w: (w.window_minutes or 0, w.label)),
    )
    return asdict(report)


def probe_adapter(record: AdapterRecord, now: datetime | None = None) -> dict[str, Any]:
    module = load_entrypoint_module(record, ACCOUNT_CAPABILITY)
    if module is None:
        return unavailable(record.id, "adapter declares no account probe")
    probe = getattr(module, PROBE_ATTRIBUTE, None)
    if not callable(probe):
        return unavailable(record.id, f"account probe exposes no {PROBE_ATTRIBUTE}()")
    try:
        raw = probe()
    except Exception as exc:  # a third-party probe must not take the route down
        logger.warning("%s account probe failed: %s", record.id, exc)
        return unavailable(record.id, f"probe raised {type(exc).__name__}")
    return normalize_report(record.id, raw, now)


def collect_account_status(
    project_root: Path | None = None, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Report every configured adapter that declares the account capability."""
    records = load_adapter_records()
    root = project_root or Path.cwd()
    configured = configured_adapter_ids(root, records)
    return [
        probe_adapter(records[adapter_id], now)
        for adapter_id in configured
        if adapter_id in records and ACCOUNT_CAPABILITY in records[adapter_id].capabilities
    ]


def auth_mode_of(adapter: str, project_root: Path | None = None) -> str:
    """The adapter's own answer to whether its spend is billed, or 'unknown'."""
    records = load_adapter_records()
    record = records.get(adapter)
    if record is None or ACCOUNT_CAPABILITY not in record.capabilities:
        return "unknown"
    return str(probe_adapter(record).get("auth_mode") or "unknown")
