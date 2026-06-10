"""board_os parser — lean task file parser.

Parses `docs/tasks/TASK-NNN-slug.md` in lean format
(YAML frontmatter + Outcome + Read First + Acceptance + Work Log).
Falls back to the legacy 12-section parser when frontmatter is absent.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    STATUS_ENUM,
)

logger = logging.getLogger("coding_os.board_os.parser")

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n(?P<body>.*)$",
    re.DOTALL,
)
_H1_RE = re.compile(r"^#\s+(?P<task_id>TASK-(?:[A-Z][A-Z0-9]*-)?\d+):\s*(?P<title>.+?)\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_OUTCOME_RE = re.compile(
    r"\*\*Outcome[^*]*\*\*\s*(?:<!--[^>]*-->\s*)?(.+?)(?:\n\n|\n##|\Z)",
    re.DOTALL,
)

_LEGACY_STATUS_MAP = {
    "open": "ready",
    "wip": "in_progress",
    "done": "complete",
    "blocked": "blocked",
}


@dataclass(frozen=True)
class ParsedTask:
    task_id: str
    title: str
    swimlane: str
    kind: str
    epic: str | None
    labels: tuple[str, ...]
    status: str
    priority: str
    appetite: str
    created: str | None = None
    started: str | None = None
    completed: str | None = None
    agent_session: str | None = None
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    blocked_by: tuple[str, ...] = field(default_factory=tuple)
    references: tuple[str, ...] = field(default_factory=tuple)
    # Optional bidirectional link to a forge issue/PR (e.g. "github#42"). Metadata
    # only — never the task's canonical id (ADR adr-task-id-allocator-seam).
    external_ref: str | None = None
    outcome: str | None = None
    read_first: tuple[str, ...] = field(default_factory=tuple)
    work_log_lines: tuple[str, ...] = field(default_factory=tuple)
    body_hash: str = ""
    source_path: str | None = None
    is_lean: bool = True
    parse_warnings: tuple[str, ...] = field(default_factory=tuple)


def is_lean_format(content: str) -> bool:
    return bool(_FRONTMATTER_RE.match(content))


def extract_frontmatter(content: str) -> dict[str, Any] | None:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group("yaml"))
    except yaml.YAMLError as exc:
        logger.debug("frontmatter YAML parse error: %s", exc)
        return None
    return data if isinstance(data, dict) else None


def detect_duplicate_frontmatter(content: str) -> str | None:
    """Flag a second task-shaped frontmatter block in the body — two blocks
    with conflicting `status:` silently skew board counts (the parser only
    ever reads the first; observed on TASK-116)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    body = m.group("body")
    m2 = re.search(r"(?:^|\n)---\s*\n(?P<yaml>.*?)\n---\s*\n", body, re.DOTALL)
    if not m2:
        return None
    try:
        dup = yaml.safe_load(m2.group("yaml"))
    except yaml.YAMLError:
        return None
    # Only a dict carrying id+status is a duplicate FRONTMATTER — a plain
    # `---` horizontal rule or a yaml snippet in the body must not flag.
    if not isinstance(dup, dict) or "id" not in dup or "status" not in dup:
        return None
    first = extract_frontmatter(content) or {}
    return (
        f"duplicate frontmatter block: first status={first.get('status')!r}, "
        f"second status={dup.get('status')!r} — merge to ONE block"
    )


def _extract_body_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(_H2_RE.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[m.group(1).strip()] = body[start:end].strip()
    return sections


def _extract_outcome(body: str) -> str | None:
    # Prefer the dedicated `## Outcome` H2 section. A blind whole-body regex
    # mis-fires on any "**Outcome**" appearing earlier — the frontmatter title
    # or the prose — so scope extraction to the section when it exists: strip an
    # optional leading "**Outcome…**" marker, then take its first real line.
    section = _extract_body_sections(body).get("Outcome")
    if section is not None:
        cleaned = re.sub(r"^\s*\*\*Outcome[^*]*\*\*\s*", "", section, count=1)
        for line in cleaned.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("<!--"):
                return stripped
        return None
    # Legacy fallback: tasks with an inline "**Outcome:**" outside any H2.
    m = _OUTCOME_RE.search(body)
    if not m:
        return None
    text = m.group(1).strip()
    if text.startswith("<!--"):
        return None
    first = text.split("\n")[0].strip()
    return first or None


def _extract_read_first_paths(body: str) -> tuple[str, ...]:
    rf = _extract_body_sections(body).get("Read First", "")
    if not rf:
        return ()
    paths: list[str] = []
    for raw in rf.splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        md = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
        if md:
            paths.append(md.group(2))
            continue
        bt = re.search(r"`([^`]+)`", line)
        if bt:
            paths.append(bt.group(1))
    return tuple(paths)


def _extract_work_log_lines(body: str) -> tuple[str, ...]:
    wl = _extract_body_sections(body).get("Work Log", "")
    if not wl:
        return ()
    return tuple(ln.strip() for ln in wl.splitlines() if ln.strip().startswith("- "))


def _validate_frontmatter(fm: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if fm.get("status") and fm["status"] not in STATUS_ENUM:
        warnings.append(f"status={fm['status']!r} not in STATUS_ENUM")
    if fm.get("kind") and fm["kind"] not in KIND_ENUM:
        warnings.append(f"kind={fm['kind']!r} not in KIND_ENUM")
    if fm.get("priority") and fm["priority"] not in PRIORITY_ENUM:
        warnings.append(f"priority={fm['priority']!r} not in PRIORITY_ENUM")
    appetite = fm.get("appetite")
    if appetite and not APPETITE_RE.match(str(appetite)):
        warnings.append(f"appetite={appetite!r} bad shape")
    labels = fm.get("labels") or []
    if isinstance(labels, list):
        for lbl in labels:
            if isinstance(lbl, str) and lbl in KIND_ENUM:
                warnings.append(f"label {lbl!r} collides with KIND_ENUM")
    return warnings


def _normalize_str_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(v) for v in value if v)
    return ()


def parse_task(content: str, *, path: Path | None = None) -> ParsedTask | None:
    source_str = str(path) if path else None
    if not is_lean_format(content):
        return _parse_legacy_fallback(content, source_str)
    fm = extract_frontmatter(content)
    if not fm:
        return _parse_legacy_fallback(content, source_str)

    m = _FRONTMATTER_RE.match(content)
    body = m.group("body") if m else ""

    task_id = fm.get("id")
    if not task_id:
        h1 = _H1_RE.search(body)
        if h1:
            task_id = h1.group("task_id")
    if not task_id:
        return None

    title = fm.get("title")
    if not title:
        h1 = _H1_RE.search(body)
        if h1:
            title = h1.group("title")

    return ParsedTask(
        task_id=str(task_id),
        title=str(title or "").strip(),
        swimlane=str(fm.get("swimlane") or ""),
        kind=str(fm.get("kind") or ""),
        epic=(str(fm["epic"]) if fm.get("epic") else None),
        labels=_normalize_str_list(fm.get("labels")),
        status=str(fm.get("status") or "icebox"),
        priority=str(fm.get("priority") or "P2"),
        appetite=str(fm.get("appetite") or "1d"),
        created=(str(fm["created"]) if fm.get("created") else None),
        started=(str(fm["started"]) if fm.get("started") else None),
        completed=(str(fm["completed"]) if fm.get("completed") else None),
        agent_session=(str(fm["agent_session"]) if fm.get("agent_session") else None),
        depends_on=_normalize_str_list(fm.get("depends_on")),
        blocked_by=_normalize_str_list(fm.get("blocked_by")),
        references=_normalize_str_list(fm.get("references")),
        external_ref=(str(fm["external_ref"]) if fm.get("external_ref") else None),
        outcome=_extract_outcome(body),
        read_first=_extract_read_first_paths(body),
        work_log_lines=_extract_work_log_lines(body),
        body_hash=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
        source_path=source_str,
        is_lean=True,
        parse_warnings=tuple(_validate_frontmatter(fm)),
    )


def _parse_legacy_fallback(content: str, source_str: str | None) -> ParsedTask | None:
    try:
        from thinking_os import task_parser as legacy  # type: ignore
    except ImportError:
        try:
            import task_parser as legacy  # type: ignore  # fallback for script invocation
        except ImportError:
            return None
    try:
        result = legacy.parse_task_file(content)
    except Exception as exc:
        logger.debug("legacy parse error: %s", exc)
        return None
    if result is None:
        return None
    task_id = getattr(result, "task_id", None)
    if not task_id:
        return None
    raw_deps = getattr(result, "dependencies", "") or ""
    if isinstance(raw_deps, list):
        deps = tuple(str(d) for d in raw_deps if re.match(r"^TASK-(?:[A-Z][A-Z0-9]*-)?\d+$", str(d)))
    elif isinstance(raw_deps, str):
        deps = tuple(re.findall(r"TASK-(?:[A-Z][A-Z0-9]*-)?\d+", raw_deps))
    else:
        deps = ()
    return ParsedTask(
        task_id=str(task_id),
        title=str(getattr(result, "title", "")),
        swimlane=(getattr(result, "domain", None) or "").lower() or "",
        kind="",
        epic=None,
        labels=(),
        status="ready",
        priority="P2",
        appetite="1d",
        depends_on=deps,
        body_hash=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        source_path=source_str,
        is_lean=False,
        parse_warnings=("parsed via legacy fallback; run `cos task-migrate` to upgrade",),
    )
