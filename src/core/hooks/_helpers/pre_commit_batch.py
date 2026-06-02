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
import signal
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

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
