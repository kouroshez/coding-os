"""Private sibling of cli.doctor — code-budget checks; import cli.doctor."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from ._doctor_shared import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
    data_root,
)

_TOP_OFFENDERS_SHOWN = 10


def _load_scanner() -> Any | None:
    # Loaded by path, not import: src/core/scripts is a live-symlinked script
    # directory in consumer projects, not a package on sys.path.
    spec = importlib.util.spec_from_file_location(
        "cos_check_file_size",
        data_root() / "core" / "scripts" / "check_file_size.py",
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        logging.getLogger("coding_os.doctor").debug("file-size scanner unavailable: %s", exc)
        return None
    return module


def _check_file_size_budget(project: Path, report: DoctorReport) -> None:
    """quality.file_size — no source file over the line backstop."""
    scanner = _load_scanner()
    if scanner is None:
        report.checks.append(
            CheckResult(
                "quality.file_size",
                SEV_WARN,
                "file-size scanner not found — check skipped",
                {},
            )
        )
        return

    result = scanner.scan(repo_root=project)
    offenders = [v for v in result["violations"] if v["tier"] == "error"]
    warned = [v for v in result["violations"] if v["tier"] == "warn"]
    ceiling = result["ceiling"]

    if offenders:
        report.checks.append(
            CheckResult(
                "quality.file_size",
                SEV_FAIL,
                (
                    f"{len(offenders)} file(s) over the {ceiling}-line backstop — "
                    "split along an existing seam (anti-overengineering.md sub-rule 6)"
                ),
                {
                    "ceiling": ceiling,
                    "warn_at": result["warn_at"],
                    "error_count": len(offenders),
                    "warn_count": len(warned),
                    "worst": offenders[:_TOP_OFFENDERS_SHOWN],
                },
            )
        )
        return

    if warned:
        report.checks.append(
            CheckResult(
                "quality.file_size",
                SEV_WARN,
                (
                    f"{len(warned)} file(s) past {result['warn_at']} lines — "
                    "find the extraction seam before adding behavior"
                ),
                {
                    "ceiling": ceiling,
                    "warn_at": result["warn_at"],
                    "warn_count": len(warned),
                    "worst": warned[:_TOP_OFFENDERS_SHOWN],
                },
            )
        )
        return

    report.checks.append(
        CheckResult(
            "quality.file_size",
            SEV_PASS,
            f"no source file exceeds {ceiling} lines",
            {"ceiling": ceiling, "warn_at": result["warn_at"]},
        )
    )
