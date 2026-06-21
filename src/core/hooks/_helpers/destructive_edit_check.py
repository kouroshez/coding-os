"""Decide whether a PreToolUse Write/Edit/MultiEdit is a large destructive edit of a load-bearing file; emit a JSON verdict {flagged, message} and always exit 0 (fail-open)."""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

_DOCS_EXCLUDE = ("docs/tasks/", "docs/_templates/", "docs/_meta/")
_DEFAULT_MIN_LINES = 12


def _not_flagged() -> int:
    json.dump({"flagged": False}, sys.stdout)
    return 0


def _min_lines() -> int:
    raw = os.environ.get("COS_DESTRUCTIVE_GUARD_MIN_LINES", "")
    try:
        value = int(raw)
        return value if value > 0 else _DEFAULT_MIN_LINES
    except ValueError:
        return _DEFAULT_MIN_LINES


def _net_removed(tool_name: str, tool_input: dict, abs_path: Path) -> int:
    if tool_name == "Edit":
        old = tool_input.get("old_string", "") or ""
        new = tool_input.get("new_string", "") or ""
        return old.count("\n") - new.count("\n")
    if tool_name == "MultiEdit":
        total = 0
        for edit in tool_input.get("edits", []) or []:
            total += (edit.get("old_string", "") or "").count("\n")
            total -= (edit.get("new_string", "") or "").count("\n")
        return total
    if tool_name == "Write":
        if not abs_path.is_file():
            return 0  # creating a new file is never destruction
        try:
            old = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        new = tool_input.get("content", "") or ""
        return old.count("\n") - new.count("\n")
    return 0


def _is_load_bearing(rel: str, abs_path: str, config_path: str) -> bool:
    if rel.startswith("docs/"):
        if "archive/" in rel or any(rel.startswith(x) for x in _DOCS_EXCLUDE):
            return False
        return True
    try:
        import yaml

        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        patterns = ((data.get("graph") or {}).get("enforce_context_on")) or []
    except (OSError, ImportError):
        patterns = []
    for pat in patterns:
        if fnmatch.fnmatchcase(rel, pat) or fnmatch.fnmatchcase(abs_path, pat):
            return True
    return False


def _provenance(root: str, rel: str) -> tuple[str, str, str, str] | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h%x09%s%x09%an%x09%ad", "--date=short", "--", rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    line = out.stdout.strip()
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return _not_flagged()

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if tool_name not in ("Edit", "MultiEdit", "Write") or not file_path:
        return _not_flagged()

    try:
        abs_path = Path(file_path).resolve()
    except OSError:
        return _not_flagged()

    removed = _net_removed(tool_name, tool_input, abs_path)
    if removed < _min_lines():
        return _not_flagged()

    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=abs_path.parent if abs_path.parent.exists() else os.getcwd(),
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return _not_flagged()
    if not root:
        return _not_flagged()

    try:
        rel = str(abs_path.relative_to(Path(root).resolve())).replace(os.sep, "/")
    except ValueError:
        return _not_flagged()  # outside the repo

    config = sys.argv[1] if len(sys.argv) > 1 else ""
    if not _is_load_bearing(rel, str(abs_path), config):
        return _not_flagged()

    prov = _provenance(root, rel)
    if prov is None:
        return _not_flagged()  # nothing committed to protect → git has no prior content
    sha, subject, author, date = prov

    message = (
        f"destructive edit — removing {removed} line(s) from {rel}\n"
        f'  last committed: {sha} "{subject}" ({author}, {date})\n'
        f"  inspect before you overwrite:  git show {sha}:{rel}   |   git log -p -3 -- {rel}"
    )
    json.dump({"flagged": True, "message": message, "removed": removed, "path": rel}, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # fail-open: a guard must never break the agent's edit
        json.dump({"flagged": False}, sys.stdout)
        sys.exit(0)
