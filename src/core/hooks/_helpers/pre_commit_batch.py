#!/usr/bin/env python3
"""Batched pre-commit check — invoke block-* hooks for every staged file.

Replaces the previous bash loop in _pre_commit_body.sh, which deadlocks
git-commit's hook environment on ≥ ~15 staged files (bash 5.x pipe IPC
issue). This script does the same job in a single Python process — no
nested subshells, no per-file fork-bomb.

Stdin: nothing.
Args: <hooks_dir> <repo_root> <file1> [<file2> ...]
Exit: 0 if every hook passes, 1 if any hook returned 2 (block).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# Hook → file pattern matcher. Skip files the hook wouldn't act on.
_HOOK_PATTERNS = {
    "block-bad-patterns.sh": (".py", ".ts", ".tsx", ".js", ".sh", ".go"),
    "block-migration-conflict.sh": ("/migrations/",),
    "validate-task-frontmatter.sh": ("docs/tasks/TASK-",),
}


def _hook_applies(hook: str, file_path: str) -> bool:
    patterns = _HOOK_PATTERNS.get(hook, ())
    if not patterns:
        return True
    return any(p in file_path or file_path.endswith(p) for p in patterns)


def _make_envelope(abs_path: Path, rel_path: str) -> str:
    try:
        content = abs_path.read_text(errors="replace")
    except OSError:
        content = ""
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": rel_path,
                "content": content,
                "new_string": content,
            },
        }
    )


def _run_hook(hook_path: Path, envelope: str, timeout_s: int = 15) -> tuple[int, str]:
    """Run hook with envelope on stdin. Returns (exit_code, combined_output).

    Redirects the delegate's stdin/stdout/stderr to temp FILES, never OS
    pipes. A delegate that backgrounds a grandchild (log writer, hub probe)
    leaves that grandchild holding the inherited stdout fd; reading a pipe to
    EOF would then block until the grandchild dies, so every staged file paid
    the full timeout and a 15+-file commit ground on for minutes. A regular
    file fd has no EOF reader, so wait() returns the instant the direct bash
    child exits and the lingering grandchild is harmless. The child still gets
    its own session (start_new_session), so a genuinely-hung DIRECT child is
    SIGKILLed by group on timeout.
    """
    with tempfile.TemporaryFile() as in_f, tempfile.TemporaryFile() as out_f:
        in_f.write(envelope.encode())
        in_f.seek(0)
        proc = subprocess.Popen(
            ["bash", str(hook_path)],
            stdin=in_f,
            stdout=out_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
            raise
        out_f.seek(0)
        out = out_f.read().decode(errors="replace")
    return proc.returncode, out


_AUDIT_COMPLETE = re.compile(
    r"^status:\s*completed\b|\*\*Status:\*\*\s+completed\b|^-\s*\[[xX]\]\s*EvidenceBundle submitted",
    flags=re.MULTILINE,
)
_AUDIT_TASK = re.compile(r"^task_id:\s*(\S+)", flags=re.MULTILINE)


def _evidence_dispatch_recorded(db_path: str, task_id: str) -> bool | None:
    # True/False = found / not-found a real exhaustive_evidence dispatch for the
    # task. None = indeterminate (no DB, error, or zero evidence history at all,
    # e.g. a fresh / CI checkout) — caller must fail-open and NOT block.
    if not db_path or not Path(db_path).is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None
    try:
        if con.execute(
            "SELECT 1 FROM formula_dispatches "
            "WHERE formula_id = 'exhaustive_evidence' AND status = 'ok' LIMIT 1"
        ).fetchone() is None:
            return None
        row = con.execute(
            "SELECT 1 FROM formula_dispatches "
            "WHERE task_marker = ? AND formula_id = 'exhaustive_evidence' "
            "AND status = 'ok' LIMIT 1",
            (task_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return row is not None


def _check_audit_evidence(abs_path: Path, rel_path: str) -> str | None:
    # Runtime-independent audit-forgery backstop (fires for human / Codex-GUI /
    # agent commits alike, since it runs in the git pre-commit). A committed
    # audit that claims completion must be backed by a real exhaustive_evidence
    # dispatch — completion comes from cos_supervise_record_output, never a
    # hand-edit (Rule 25; the Stop guardian trusts the DB row, not the file).
    # Fail-open everywhere; COS_ALLOW_AUDIT_EDIT=1 is the explicit escape.
    if os.environ.get("COS_ALLOW_AUDIT_EDIT") == "1":
        return None
    try:
        text = abs_path.read_text(errors="replace")
    except OSError:
        return None
    if not _AUDIT_COMPLETE.search(text):
        return None
    m = _AUDIT_TASK.search(text)
    if not m:
        return None
    task_id = m.group(1)
    if _evidence_dispatch_recorded(os.environ.get("COS_DB_PATH", ""), task_id) is False:
        return (
            f"BLOCKED [audit-evidence] {rel_path}: claims completion but no "
            f"exhaustive_evidence dispatch for {task_id} in formula_dispatches.\n"
            "  An audit's completion must come from cos_supervise_record_output, "
            "not a hand-edit (the Stop guardian trusts the DB row, not the file).\n"
            "  Legit completion: run cos_supervise_record_output first. "
            "Override: COS_ALLOW_AUDIT_EDIT=1."
        )
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(
            "usage: pre_commit_batch.py <hooks_dir> <repo_root> <file1> [<file2> ...]",
            file=sys.stderr,
        )
        return 2

    hooks_dir = Path(argv[1]).resolve()
    repo_root = Path(argv[2]).resolve()
    rel_files = argv[3:]

    failed = False
    for rel_path in rel_files:
        abs_path = (repo_root / rel_path).resolve()
        if not abs_path.is_file():
            continue
        envelope = _make_envelope(abs_path, rel_path)

        # Always run block-* hooks; conditionally run validate-task-frontmatter.
        for hook_name in ("block-bad-patterns.sh", "block-migration-conflict.sh"):
            hook_path = hooks_dir / hook_name
            if not hook_path.is_file():
                continue
            if not _hook_applies(hook_name, rel_path):
                continue
            try:
                code, out = _run_hook(hook_path, envelope)
            except subprocess.TimeoutExpired:
                print(f"BLOCKED [{hook_name}] {rel_path}: timed out after 15s", file=sys.stderr)
                failed = True
                continue
            if code == 2:
                print(f"BLOCKED [{hook_name}] {rel_path}:", file=sys.stderr)
                print(out.strip(), file=sys.stderr)
                failed = True

        if rel_path.startswith("docs/tasks/TASK-"):
            hook_path = hooks_dir / "validate-task-frontmatter.sh"
            if hook_path.is_file():
                try:
                    code, out = _run_hook(hook_path, envelope)
                except subprocess.TimeoutExpired:
                    print(f"BLOCKED [task-frontmatter] {rel_path}: timed out", file=sys.stderr)
                    failed = True
                    continue
                if code == 2:
                    print(f"BLOCKED [task-frontmatter] {rel_path}:", file=sys.stderr)
                    print(out.strip(), file=sys.stderr)
                    failed = True

        if rel_path.startswith("docs/tasks/audits/audit-") and rel_path.endswith(".md"):
            audit_msg = _check_audit_evidence(abs_path, rel_path)
            if audit_msg:
                print(audit_msg, file=sys.stderr)
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
