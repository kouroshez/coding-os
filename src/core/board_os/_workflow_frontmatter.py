"""board_os workflow — task-file frontmatter reads and atomic writes.

Targeted regex field-patching rather than a YAML round-trip, so inline comments
and key order survive; every write goes through tempfile + os.replace.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path

import yaml


def _parse_labels(raw: object) -> set[str]:
    """Normalize a task's labels_json column into a set of label strings.

    Accepts the JSON-array string the DB stores, a real list, or None.
    """
    if not raw:
        return set()
    if isinstance(raw, (list, tuple)):
        return {str(x) for x in raw}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return set()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {t.strip() for t in text.split(",") if t.strip()}
        if isinstance(parsed, list):
            return {str(x) for x in parsed}
    return set()


def _extract_kind_from_frontmatter(content: str) -> str | None:
    """Pull `kind:` from YAML frontmatter without dragging in PyYAML.

    Frontmatter lives between two `---` lines at file head. Returns the
    raw value as written; defaults to None when absent or malformed.
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end < 0:
        return None
    head = content[3:end]
    for line in head.splitlines():
        line = line.strip()
        if line.startswith("kind:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'") or None
    return None


def _patch_fm_field(fm_text: str, key: str, value: str) -> str:
    """Replace a scalar field in raw YAML text without touching comments or key order.

    If the key already exists, its value is updated in-place.
    If it is absent, the key is appended on a new line (handles tasks
    created before a field was added to the template).
    """
    import re as _re

    pattern = _re.compile(rf"^({_re.escape(key)}:)[ \t]*.*$", _re.MULTILINE)
    if pattern.search(fm_text):
        return pattern.sub(rf"\1 {value}", fm_text, count=1)
    return fm_text + f"\n{key}: {value}"


def _write_status_to_frontmatter(
    path: Path,
    new_status: str,
    *,
    agent_session: str | None,
) -> None:
    """Atomically update status (+ started/completed timestamps) in frontmatter.

    Uses targeted regex field-patching instead of YAML round-trip so that
    inline comments (e.g. ``# always start here``) are preserved verbatim.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    content = path.read_text(encoding="utf-8")
    import re as _re

    fm_re = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{path}: no frontmatter to update")

    fm_raw = m.group(1)

    # Validate YAML is parseable before touching anything.
    try:
        fm_parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter YAML broken: {exc}") from exc
    if not isinstance(fm_parsed, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")

    today = time.strftime("%Y-%m-%d")
    fm_raw = _patch_fm_field(fm_raw, "status", new_status)
    if agent_session is not None:
        fm_raw = _patch_fm_field(fm_raw, "agent_session", agent_session)
    if new_status == "in_progress" and not fm_parsed.get("started"):
        fm_raw = _patch_fm_field(fm_raw, "started", today)
    if new_status == "complete" and not fm_parsed.get("completed"):
        fm_raw = _patch_fm_field(fm_raw, "completed", today)

    new_content = f"---\n{fm_raw}\n---\n" + content[m.end() :]

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".task-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _format_yaml_scalar_token(value: str) -> str:
    """Format a scalar for YAML frontmatter (unquoted id vs JSON-quoted string)."""
    import re as _re

    if _re.match(r"^[a-z0-9][a-z0-9-]*$", value, _re.I):
        return value
    return json.dumps(value)


def patch_task_frontmatter_scalars(path: Path, updates: dict[str, str]) -> None:
    if not updates:
        return
    if not path.exists():
        raise FileNotFoundError(str(path))

    content = path.read_text(encoding="utf-8")
    import re as _re

    fm_re = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{path}: no frontmatter to update")

    fm_raw = m.group(1)
    try:
        fm_parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter YAML broken: {exc}") from exc
    if not isinstance(fm_parsed, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")

    for key, raw_val in updates.items():
        token = _format_yaml_scalar_token(raw_val)
        fm_raw = _patch_fm_field(fm_raw, key, token)

    new_content = f"---\n{fm_raw}\n---\n" + content[m.end() :]

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".task-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
