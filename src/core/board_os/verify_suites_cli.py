"""CLI dispatcher for verify-suite enforcement (TASK-100)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
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


# Paths whose churn must NOT invalidate a recorded suite PASS: work-log
# appends land in docs/tasks/** on every code edit, and .coding-os/** is
# live agent state — neither can change pytest outcomes.
_DIGEST_EXCLUDES = ("docs/tasks/", ".coding-os/")


def _tree_state(repo_root: Path | None = None) -> dict[str, str]:
    cwd = str(repo_root or Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())))

    def _git(*git_args: str) -> bytes:
        try:
            proc = subprocess.run(["git", *git_args], capture_output=True, cwd=cwd, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return b""
        return proc.stdout if proc.returncode == 0 else b""

    head = _git("rev-parse", "HEAD").decode("utf-8", "replace").strip()
    if not head:
        return {"git_head": "", "dirty_digest": ""}
    exclude_specs = [f":(exclude){p.rstrip('/')}" for p in _DIGEST_EXCLUDES]
    diff = _git("diff", "HEAD", "--", ".", *exclude_specs)
    untracked = sorted(
        p
        for p in _git("ls-files", "--others", "--exclude-standard")
        .decode("utf-8", "replace")
        .splitlines()
        if p and not p.startswith(_DIGEST_EXCLUDES)
    )
    if not diff and not untracked:
        return {"git_head": head, "dirty_digest": "clean"}
    payload = diff + b"\x00" + "\n".join(untracked).encode("utf-8")
    return {"git_head": head, "dirty_digest": hashlib.sha1(payload).hexdigest()}


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
    tree = _tree_state()

    missing: list[str] = []
    ok: list[str] = []
    for suite in required:
        rule = cfg.suites.get(suite)
        max_age = rule.max_age_seconds if rule and rule.max_age_seconds else default_age
        entry = data.get(suite, {})
        status = entry.get("status")
        ts = entry.get("ts", 0)
        age = now - int(ts) if isinstance(ts, int) else max_age + 1
        if tree["git_head"]:
            # Commit-keyed freshness: a PASS recorded on a different tree
            # (other HEAD, or other dirty content) proves nothing about this
            # one. v1 entries lack the keys and are therefore always stale.
            tree_match = (
                entry.get("git_head") == tree["git_head"]
                and entry.get("dirty_digest") == tree["dirty_digest"]
            )
        else:
            # No git available — degrade to v1 time-only freshness (fail-open).
            tree_match = True
        if status == "PASS" and age <= max_age and tree_match:
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


def cmd_tree_state(args: argparse.Namespace) -> int:
    print(json.dumps(_tree_state()))
    return 0


def _command_paths(cmd: str) -> set[str]:
    return {tok.rstrip("/") for tok in cmd.split() if "/" in tok and not tok.startswith("-")}


_WRAPPER_TOKENS = ("nice", "time", "/usr/bin/time", "caffeinate")


def _command_segments(cmd: str) -> list[list[str]]:
    """Split a shell command into logical segments, wrappers stripped.

    Segment-anchored matching keeps a quoted suite command (heredoc body,
    commit message, doc edit) from being mistaken for an actual run.
    """
    segments: list[list[str]] = []
    for part in re.split(r"&&|\|\||[;|\n]", cmd):
        toks = part.split()
        while toks:
            head = toks[0]
            if "=" in head and not head.startswith("-"):
                toks = toks[1:]  # leading env assignment
            elif head in _WRAPPER_TOKENS:
                toks = toks[1:]
                while toks and toks[0].startswith("-"):
                    takes_value = toks[0] == "-n" and len(toks) > 1
                    toks = toks[2:] if takes_value else toks[1:]
            else:
                break
        if toks:
            segments.append(toks)
    return segments


def _pytest_segments(cmd: str) -> list[list[str]]:
    """Segments that genuinely invoke pytest (not merely mention it)."""
    out = []
    for seg in _command_segments(cmd):
        head = seg[0]
        is_pytest = head == "pytest" or head.endswith("/pytest")
        is_uv = head == "uv" or head.endswith("/uv")
        if is_pytest or (is_uv and "pytest" in seg):
            out.append(seg)
        elif head in ("python", "python3") and "-m" in seg and "pytest" in seg:
            out.append(seg)
    return out


def _match_suite_command(cmd: str, cfg) -> str | None:
    """Map a shell command to the suite it executes, or None."""
    pytest_segs = _pytest_segments(cmd)
    make_segs = [s for s in _command_segments(cmd) if s[0] == "make"]
    for name, rule in cfg.suites.items():
        rule_cmd = " ".join(rule.command.split())
        if rule_cmd.startswith("make "):
            target = rule_cmd.split()[1]
            if any(target in seg for seg in make_segs):
                return name
            continue
        rule_paths = _command_paths(rule_cmd)
        if not rule_paths:
            continue
        for seg in pytest_segs:
            if rule_paths <= _command_paths(" ".join(seg)):
                return name
    return None


def _is_full_sweep(cmd: str) -> bool:
    """True for pytest invocations that would run (nearly) everything."""
    for seg in _pytest_segments(cmd):
        if "--collect-only" in seg or "--co" in seg:
            continue
        after = seg[seg.index("pytest") + 1 :]
        paths = [t for t in after if not t.startswith("-") and ("/" in t or t == "tests")]
        if not paths:
            return True  # bare pytest → testpaths = the whole repo
        if any(p.rstrip("/") == "tests" for p in paths):
            return True  # the 1,316-test integration root
        test_roots = {p.rstrip("/") for p in paths if p.rstrip("/").endswith("tests")}
        if len(test_roots) >= 3:
            return True
    return False


def cmd_match_command(args: argparse.Namespace) -> int:
    try:
        cfg = load_verify_suites()
    except VerifySuitesError:
        print(json.dumps({"suite": None, "full_sweep": False, "fresh": False}))
        return 0
    command = args.command
    suite = _match_suite_command(command, cfg)
    out: dict = {
        "suite": suite,
        "full_sweep": _is_full_sweep(command),
        "pytest_invocation": bool(_pytest_segments(command)),
        "fresh": False,
    }
    verify_file = Path(args.verify_file)
    if suite and verify_file.exists():
        missing, fresh_ok = _check_suites([suite], verify_file)
        out["fresh"] = suite in fresh_ok
        if out["fresh"]:
            try:
                entry = json.loads(verify_file.read_text(encoding="utf-8")).get(suite, {})
            except (OSError, json.JSONDecodeError):
                entry = {}
            out["recorded_by"] = entry.get("agent") or "unknown"
            out["session_tail"] = entry.get("session_tail", "")
            ts = entry.get("ts", 0)
            out["age_min"] = max(0, int((time.time() - ts) / 60)) if isinstance(ts, int) else 0
    print(json.dumps(out))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_suites_cli",
        description="Verify-suite resolver/checker.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="Read changed paths from stdin and enforce.")
    p_check.add_argument(
        "--verify-file",
        default=os.path.join(os.environ.get("COS_STATE_DIR", ".coding-os"), ".last-verify.json"),
    )
    p_check.add_argument("--verbose", action="store_true")
    p_check.set_defaults(fn=cmd_check)

    p_tree = sub.add_parser(
        "tree-state",
        help="Print {git_head, dirty_digest} JSON for the current worktree.",
    )
    p_tree.set_defaults(fn=cmd_tree_state)

    p_match = sub.add_parser(
        "match-command",
        help="Map a shell command to its suite + full-sweep/freshness verdict (JSON).",
    )
    p_match.add_argument("--command", required=True)
    p_match.add_argument(
        "--verify-file",
        default=os.path.join(os.environ.get("COS_STATE_DIR", ".coding-os"), ".last-verify.json"),
    )
    p_match.set_defaults(fn=cmd_match_command)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
