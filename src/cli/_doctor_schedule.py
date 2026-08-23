"""doctor check: the nightly scheduled run — plist state and last-run health.

Private sibling of cli.doctor; the check is re-exported by
`cli.doctor_checks_runtime`.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from ._doctor_shared import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)

logger = logging.getLogger(__name__)


def _check_scheduled(project: Path, report: DoctorReport) -> None:
    """scheduled.cron_configured — nightly cron: plist installed + loaded, no failures, run < 2d ago."""
    import datetime as _datetime
    import platform as _platform

    plist_dest = Path.home() / "Library" / "LaunchAgents" / "com.codingos.nightly.plist"
    last_run_path = project / ".coding-os" / "scheduled" / "last_run.json"
    is_macos = _platform.system() == "Darwin"
    plist_ok = True

    if is_macos:
        if not plist_dest.exists():
            report.checks.append(
                CheckResult(
                    "scheduled.cron_configured",
                    SEV_WARN,
                    "nightly cron not installed — run `cos cron install`",
                    {"plist": str(plist_dest)},
                )
            )
            return
        try:
            r = subprocess.run(
                ["launchctl", "list", "com.codingos.nightly"],
                capture_output=True,
                timeout=5,
            )
            if r.returncode != 0:
                report.checks.append(
                    CheckResult(
                        "scheduled.cron_configured",
                        SEV_WARN,
                        "plist present but not loaded — run `cos cron install`",
                        {"plist": str(plist_dest)},
                    )
                )
                return
        except OSError as exc:
            logger.debug("launchctl probe failed: %s", exc)
            plist_ok = False

    if not last_run_path.exists():
        prefix = "plist installed + loaded" if (is_macos and plist_ok) else "cron configured"
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_PASS,
                f"{prefix}, no run yet — run `cos cron run` to test",
            )
        )
        return

    try:
        data = json.loads(last_run_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_WARN,
                f"cannot read last_run.json: {exc}",
                {"path": str(last_run_path)},
            )
        )
        return

    disabled = data.get("disabled_reason")
    if disabled:
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_FAIL,
                f"auto-disabled: {disabled} — run `cos cron run --reset-failures`",
                {"disabled_reason": disabled, "last_error": data.get("last_error")},
            )
        )
        return

    failures = int(data.get("consecutive_failures") or 0)
    if failures >= 3:
        report.checks.append(
            CheckResult(
                "scheduled.cron_configured",
                SEV_FAIL,
                f"{failures} consecutive failures — run `cos cron run --reset-failures`",
                {"consecutive_failures": failures, "last_error": data.get("last_error")},
            )
        )
        return

    run_at = (data.get("run_at") or "")[:19]
    if run_at:
        try:
            run_dt = _datetime.datetime.fromisoformat(run_at)
            if run_dt.tzinfo is None:
                run_dt = run_dt.replace(tzinfo=_datetime.timezone.utc)
            now = _datetime.datetime.now(_datetime.timezone.utc)
            age_days = (now - run_dt).total_seconds() / 86400
            if age_days > 2:
                report.checks.append(
                    CheckResult(
                        "scheduled.cron_configured",
                        SEV_WARN,
                        f"last run {age_days:.1f}d ago — is launchd running?",
                        {"run_at": run_at, "age_days": round(age_days, 1)},
                    )
                )
                return
        except (ValueError, TypeError) as exc:
            logger.debug("run_at parse failed: %s", exc)

    parts: list[str] = []
    if is_macos and plist_ok:
        parts.append("plist loaded")
    if failures:
        parts.append(f"failures={failures}")
    if run_at:
        parts.append(f"last={run_at[:10]}")
    report.checks.append(
        CheckResult(
            "scheduled.cron_configured",
            SEV_PASS,
            ", ".join(parts) if parts else "healthy",
            {"consecutive_failures": failures, "run_at": run_at or None},
        )
    )
