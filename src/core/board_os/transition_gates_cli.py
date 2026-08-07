"""Thin CLI wrapper around the transition-gates validator (TASK-105)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

from board_os.parser import extract_frontmatter, parse_task
from board_os.transition_gates import GatesConfigError, load_gates_config
from board_os.transition_gates_validator import (
    ValidationResult,
    Verdict,
    validate_transition,
)

logger = logging.getLogger("coding_os.board_os.gates")


def _read_stdin_payload() -> dict:
    """Read the hook payload from stdin (≤2 s timeout matches our hooks)."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _load_body_for_task(task_id: str, file_path: Path | None) -> tuple[str, str]:
    """Return (body, kind) for an existing task. Falls back to ('', 'feature')."""
    if file_path and file_path.exists():
        content = file_path.read_text(encoding="utf-8")
        fm = extract_frontmatter(content) or {}
        kind = str(fm.get("kind") or "feature")
        return content, kind

    # Fallback: query DB via canonical resolver.
    try:
        from thinking_os.database import resolve_db_path  # type: ignore

        db_path = str(resolve_db_path())
    except ImportError:
        db_path = os.environ.get("COS_DB_PATH") or ""
    if not db_path or not Path(db_path).exists():
        return "", "feature"
    # Route through get_connection for WAL + busy_timeout.
    try:
        from thinking_os.database import get_connection  # type: ignore

        conn = get_connection(db_path)
    except Exception:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
    try:
        row = conn.execute(
            "SELECT file_path, kind FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return "", "feature"
    fp = Path(row[0]) if row[0] else None
    if fp and fp.exists():
        return fp.read_text(encoding="utf-8"), str(row[1] or "feature")
    return "", str(row[1] or "feature")


def _verify_ledger_path() -> Path | None:
    state_dir = Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
    if state_dir.is_absolute():
        return state_dir / ".last-verify.json"
    try:
        from thinking_os.database import project_root  # type: ignore

        return project_root() / state_dir / ".last-verify.json"
    except Exception as exc:
        logger.debug("project-root ledger resolution unavailable: %s", exc)
        return state_dir / ".last-verify.json"


def _verify_state() -> tuple[bool, int | None]:
    """Most-recent PASS in .last-verify.json (freshness gate, not a forge wall).

    Intentionally keys on status==PASS + recency only, NOT git_head/dirty_digest:
    the working tree legitimately changes between the verify run and task-close
    (work-log edits + the code commit land between them), so binding the record to
    the tree would block every honest close. The record is also written by the same
    actor it gates (record-verify runs as the agent), so this is defense-in-depth —
    it catches the FORGOTTEN run, not a deliberate forge. The real wall is the
    server-side required CI check in pr-mode, not this local marker. (TASK-620)
    """
    # COS_STATE_DIR is routinely a RELATIVE path, so resolving it against the
    # gate process's cwd read a different file than the verify runners wrote —
    # the MCP/board process does not share the agent's working directory. Anchor
    # it to the project root, the same way every other kernel path is resolved.
    path = _verify_ledger_path()
    if path is None or not path.exists():
        return False, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    now = int(time.time())
    most_recent: int | None = None
    for suite_data in data.values():
        if not isinstance(suite_data, dict):
            continue
        if suite_data.get("status") != "PASS":
            continue
        ts = suite_data.get("ts")
        if isinstance(ts, int) and (most_recent is None or ts > most_recent):
            most_recent = ts
    if most_recent is None:
        return False, None
    return True, max(0, now - most_recent)


def _has_work_log_entries(body: str) -> bool:
    parsed = parse_task(body)
    return bool(parsed and parsed.work_log_lines)


def _emit_messages(result: ValidationResult) -> None:
    for msg in result.messages:
        prefix = {
            Verdict.BLOCK: "BLOCKED",
            Verdict.WARN: "WARN",
            Verdict.PASS: "INFO",
        }[msg.severity]
        print(f"  [{msg.code}] {prefix}: {msg.message}", file=sys.stderr)


def cmd_check(args: argparse.Namespace) -> int:
    """Validate a transition. Reads task file from --task-file or --task-id."""
    try:
        config = load_gates_config()
    except GatesConfigError as exc:
        print(
            f"BLOCKED: transition-gates config error: {exc}",
            file=sys.stderr,
        )
        return 2

    body: str = ""
    kind: str = args.kind or "feature"

    if args.task_file:
        path = Path(args.task_file)
        if path.exists():
            body = path.read_text(encoding="utf-8")
            fm = extract_frontmatter(body) or {}
            if not args.kind:
                kind = str(fm.get("kind") or "feature")
    elif args.task_id:
        body, k = _load_body_for_task(args.task_id, None)
        if not args.kind:
            kind = k

    if not body and not args.allow_empty:
        print(
            "BLOCKED: no task body resolved (pass --task-file PATH or --task-id TASK-NNN).",
            file=sys.stderr,
        )
        return 2

    has_recent, age = _verify_state()
    has_work_log = _has_work_log_entries(body)

    result = validate_transition(
        task_id=args.task_id or "(unknown)",
        kind=kind,
        body=body,
        new_status=args.new_status,
        config=config,
        has_recent_verify=has_recent,
        verify_age_seconds=age,
        has_work_log=has_work_log,
        override_reason=os.environ.get("COS_OVERRIDE_REASON"),
        override_actor=os.environ.get("COS_AGENT"),
    )

    _emit_messages(result)
    if args.json:
        print(result.model_dump_json())
    return 2 if result.blocked else 0


def cmd_check_payload(args: argparse.Namespace) -> int:
    """Hook entry point: read Claude Code hook JSON from stdin."""
    payload = _read_stdin_payload()
    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if not file_path or "docs/tasks/TASK-" not in file_path:
        return 0  # not a task edit — pass

    # Reconstruct what the file WILL look like after the Edit (so we
    # validate the proposed body, not the current one).
    if "new_string" in tool_input and "old_string" in tool_input:
        path = Path(file_path)
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8").replace(
                    tool_input["old_string"],
                    tool_input["new_string"],
                )
            except Exception:
                content = path.read_text(encoding="utf-8")
        else:
            content = tool_input["new_string"]
    else:
        content = tool_input.get("content", "")

    fm = extract_frontmatter(content) or {}
    new_status = str(fm.get("status") or "")
    kind = str(fm.get("kind") or "feature")
    task_id = str(fm.get("id") or "")

    if new_status not in {"in_progress", "complete"}:
        return 0  # gates only fire on these transitions

    try:
        config = load_gates_config()
    except GatesConfigError as exc:
        print(f"BLOCKED: transition-gates config error: {exc}", file=sys.stderr)
        return 2

    has_recent, age = _verify_state()
    has_work_log = _has_work_log_entries(content)

    result = validate_transition(
        task_id=task_id,
        kind=kind,
        body=content,
        new_status=new_status,
        config=config,
        has_recent_verify=has_recent,
        verify_age_seconds=age,
        has_work_log=has_work_log,
        override_reason=os.environ.get("COS_OVERRIDE_REASON"),
        override_actor=os.environ.get("COS_AGENT"),
    )

    _emit_messages(result)
    if result.blocked:
        print(
            "  Override (with reason): COS_DOR_OVERRIDE=1 COS_OVERRIDE_REASON='...' (>= 15 chars)",
            file=sys.stderr,
        )
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transition_gates_cli",
        description="Transition-gates validator dispatcher.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Validate a manually-specified transition.")
    p_check.add_argument("--task-id")
    p_check.add_argument("--task-file")
    p_check.add_argument("--kind")
    p_check.add_argument("--new-status", required=True)
    p_check.add_argument("--allow-empty", action="store_true")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(fn=cmd_check)

    p_payload = sub.add_parser(
        "check-payload",
        help="Read Claude Code hook JSON from stdin and validate the proposed Edit.",
    )
    p_payload.set_defaults(fn=cmd_check_payload)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
