"""CLI dispatcher for verify-suite enforcement (Phase L.10 / TASK-100)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from board_os.transition_gates import load_gates_config
from board_os.transition_gates_validator import (
    Verdict,
    evaluate_override,
)
from board_os.verify_suites import (
    VerifySuitesError,
    load_verify_suites,
    match_suites,
)


def _read_changed_paths() -> list[str]:
    raw = sys.stdin.read()
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _check_suites(required: list[str], verify_file: Path) -> tuple[list[str], list[str]]:
    """Return (missing_or_stale, ok_suites)."""
    if not verify_file.exists():
        return required, []
    try:
        data = json.loads(verify_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return required, []

    now = int(time.time())
    cfg = load_verify_suites()
    default_age = int(cfg.defaults.get("max_age_seconds", 1800))

    missing: list[str] = []
    ok: list[str] = []
    for suite in required:
        rule = cfg.suites.get(suite)
        max_age = rule.max_age_seconds if rule and rule.max_age_seconds else default_age
        entry = data.get(suite, {})
        status = entry.get("status")
        ts = entry.get("ts", 0)
        age = now - int(ts) if isinstance(ts, int) else max_age + 1
        if status == "PASS" and age <= max_age:
            ok.append(suite)
        else:
            missing.append(suite)
    return missing, ok


def cmd_check(args: argparse.Namespace) -> int:
    try:
        cfg = load_verify_suites()
    except VerifySuitesError as exc:
        print(f"BLOCKED: verify-suites config error: {exc}", file=sys.stderr)
        return 2

    changed = _read_changed_paths()
    if not changed:
        # No changes — allow.
        return 0

    required = match_suites(changed, cfg)
    if not required:
        # No suite covers these paths — allow but log via stderr in
        # verbose mode (so retro reviewers can spot orphan path classes).
        if args.verbose:
            print(
                "  [info] no verify suite matches changed paths: "
                + ", ".join(changed[:5])
                + ("…" if len(changed) > 5 else ""),
                file=sys.stderr,
            )
        return 0

    verify_file = Path(args.verify_file)
    missing, _ok = _check_suites(required, verify_file)

    if not missing:
        return 0

    # Check override.
    if os.environ.get("COS_VERIFY_OVERRIDE") == "1":
        gates_cfg = load_gates_config()
        override_result, _ = evaluate_override(
            "verify",
            reason=os.environ.get("COS_OVERRIDE_REASON"),
            actor=os.environ.get("COS_AGENT"),
            config=gates_cfg,
        )
        if override_result.verdict is not Verdict.BLOCK:
            print(
                "  [VERIFY_OVERRIDDEN] WARN: required suites not run, "
                "but override was accepted with reason. Recorded for retro audit.",
                file=sys.stderr,
            )
            return 0
        for m in override_result.messages:
            print(f"  [{m.code}] {m.message}", file=sys.stderr)

    print("BLOCKED: Required verifications not satisfied. Run:", file=sys.stderr)
    for suite in missing:
        rule = cfg.suites.get(suite)
        cmd = rule.command if rule else f"make {suite}"
        print(f"  {cmd}", file=sys.stderr)
    print(
        f"  Changed paths matched suites: {required}",
        file=sys.stderr,
    )
    print(
        "  Override (audited): COS_VERIFY_OVERRIDE=1 COS_OVERRIDE_REASON='...≥15 chars'",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_suites_cli",
        description="Phase L.10 verify-suite resolver/checker.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="Read changed paths from stdin and enforce.")
    p_check.add_argument(
        "--verify-file",
        default=os.path.join(os.environ.get("COS_STATE_DIR", ".coding-os"), ".last-verify.json"),
    )
    p_check.add_argument("--verbose", action="store_true")
    p_check.set_defaults(fn=cmd_check)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
