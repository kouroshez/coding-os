"""
Coding OS — Task detail file parser (Phase C.2).

Pure, stateless parser for `docs/tasks/TASK-###-slug.md` files produced by
`cos task-create`. No DB dependency — fully unit-testable without any
side effects.

Expected section layout (from docs/governance/task-lifecycle.md):
    <!-- domain:BACKEND | layer:task | ssot:true | updated:... -->
    # TASK-NNN: [DOMAIN] Title

    Purpose: ...
    Read when: ...
    Skip when: ...

    > Nav: ...

    - Created: YYYY-MM-DD

    ## Goal
    ## Read First
    ## Source of Truth
    ## Scope
    ### In
    ### Out
    ## Requirements
    ## Dependencies
    ## Open Questions
    ## Rabbit Holes
    ## Verification
    ## Notes             (optional)

Public API:
    parse_task_file(content: str) -> ParsedTask | None
    extract_task_id_from_h1(h1_text: str) -> tuple[str, str | None, str]
    extract_dependencies(section_text: str) -> list[str]

All helpers are pure functions.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("coding_os.task_parser")

# Front-matter header to strip before parsing (same convention as doc_indexer).
_FRONT_MATTER_RE = re.compile(r"^<!--\s*domain:[^>]*-->\s*\n?", re.MULTILINE)

# YAML front-matter block (Phase M: intensity/persona/situation fields).
_YAML_FM_RE = re.compile(r"^---\s*\n(?P<yaml>.*?)\n---\s*\n", re.DOTALL)

# Heading detection
_H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^### (.+)$", re.MULTILINE)

# H1 shape: "TASK-199: [BACKEND] Commission model"
# Captures: (task_id_number, optional_domain_tag, title_text)
_H1_TASK_RE = re.compile(r"^TASK-(\d+):\s*(?:\[([A-Z0-9_-]+)\]\s*)?(.+?)\s*$")

# Bulleted list line: "- content"
_BULLET_RE = re.compile(r"^-\s+(.+?)\s*$", re.MULTILINE)

# Numbered list line: "1. content", "2. content", ...
_NUMBERED_RE = re.compile(r"^\d+\.\s+(.+?)\s*$", re.MULTILINE)

# TASK reference: "TASK-195" or "TASK-001"
_TASK_REF_RE = re.compile(r"\bTASK-(\d+)\b")


@dataclass(frozen=True)
class ParsedTask:
    """Structured view of a task detail file.

    Immutable so callers can't accidentally mutate parsed state — matches
    the project-wide preference for immutable data (see coding-style rule).
    """

    task_id: str  # "TASK-199" (canonical, zero-padded to 3)
    title: str  # "Commission model" (without prefix + domain tag)
    raw_title: str  # "TASK-199: [BACKEND] Commission model"
    domain: str | None  # "BACKEND" (from [DOMAIN] tag)
    goal_text: str  # first paragraph of ## Goal
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    source_of_truth: list[str] = field(default_factory=list)
    read_first: list[str] = field(default_factory=list)
    open_questions: str = ""
    rabbit_holes: str = ""
    verification: str = ""
    content_hash: str = ""
    # Phase M: optional cognitive routing fields from YAML frontmatter
    intensity: str | None = None  # light | standard | full
    persona: str | None = None  # e.g. senior-backend, tech-lead
    situation: str | None = None  # e.g. incident-response, onboarding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_yaml_frontmatter(content: str) -> dict:
    """Extract Phase M cognitive routing fields from YAML frontmatter.

    Returns a dict with `intensity`, `persona`, `situation` (all Optional[str]).
    Silently returns empty dict if frontmatter absent or yaml import unavailable.
    """
    m = _YAML_FM_RE.match(content)
    if not m:
        return {}
    try:
        import yaml  # optional dep; not required for legacy task parsing

        data = yaml.safe_load(m.group("yaml")) or {}
    except Exception:
        return {}
    result = {}
    for key in ("intensity", "persona", "situation"):
        val = data.get(key)
        if val is not None:
            result[key] = str(val)
    return result


def _strip_front_matter(content: str) -> str:
    """Remove a leading `<!-- domain:... -->` HTML comment header.

    Only strips the very first match so a legitimate comment later in the
    body (e.g. inside a code fence) is preserved.
    """
    return _FRONT_MATTER_RE.sub("", content, count=1)


def _compute_content_hash(content: str) -> str:
    """Return the first 16 hex chars of SHA256(content).

    Matches `embeddings._compute_text_hash` and `capture._compute_content_hash`
    so the whole codebase shares one hashing convention.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def extract_task_id_from_h1(h1_text: str) -> tuple[str | None, str | None, str]:
    """Parse the H1 text of a task file into (task_id, domain, title).

    Examples:
        'TASK-199: [BACKEND] Commission model'
            → ('TASK-199', 'BACKEND', 'Commission model')
        'TASK-3: Simple task without domain tag'
            → ('TASK-003', None, 'Simple task without domain tag')
        'Not a task heading'
            → (None, None, 'Not a task heading')

    Args:
        h1_text: The text content of the H1 (without the leading `# `).

    Returns:
        A tuple (task_id, domain, title). `task_id` and `domain` are None if
        the H1 does not match the TASK-### pattern.
    """
    match = _H1_TASK_RE.match(h1_text.strip())
    if match is None:
        return None, None, h1_text.strip()

    number_raw, domain_raw, title_raw = match.groups()
    task_id = f"TASK-{int(number_raw):03d}"
    domain = domain_raw.upper() if domain_raw else None
    return task_id, domain, title_raw.strip()


def extract_dependencies(section_text: str) -> list[str]:
    """Extract TASK-### references from a Dependencies section body.

    Deduplicates while preserving first-appearance order. Returns an empty
    list if the section is missing, empty, or contains only "None.".

    Args:
        section_text: Raw text of the `## Dependencies` section body.

    Returns:
        List of canonical task_id strings (zero-padded).
    """
    if not section_text or section_text.strip().lower() in {"none.", "none"}:
        return []

    seen: set[str] = set()
    ordered: list[str] = []
    for match in _TASK_REF_RE.finditer(section_text):
        canonical = f"TASK-{int(match.group(1)):03d}"
        if canonical in seen:
            continue
        seen.add(canonical)
        ordered.append(canonical)
    return ordered


def _split_sections(body: str) -> dict[str, str]:
    """Split markdown body into a dict of {section_heading_lower: section_body}.

    Uses H2 as the section delimiter. Heading names are lowercased so the
    lookup is case-insensitive. Body of each section is everything up to
    the next H2 or EOF, stripped of leading/trailing whitespace.
    """
    matches = list(_H2_RE.finditer(body))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[heading] = body[start:end].strip()
    return sections


def _extract_first_paragraph(text: str) -> str:
    """Return the first paragraph (content before first `\\n\\n` or EOF)."""
    if not text:
        return ""
    paragraphs = text.split("\n\n", 1)
    return paragraphs[0].strip()


def _parse_bullets(section_text: str) -> list[str]:
    """Extract items from a bulleted list. Empty list if no bullets found."""
    if not section_text:
        return []
    return [m.group(1).strip() for m in _BULLET_RE.finditer(section_text)]


def _parse_numbered(section_text: str) -> list[str]:
    """Extract items from a numbered list. Empty list if no numbers found."""
    if not section_text:
        return []
    return [m.group(1).strip() for m in _NUMBERED_RE.finditer(section_text)]


def _parse_scope(scope_section: str) -> tuple[list[str], list[str]]:
    """Split the `## Scope` body into (in_items, out_items) by H3 subsections.

    If the section has no H3 headings, both lists are empty. Callers that
    need to handle "flat Scope without In/Out" can merge the scope text into
    one of the sublists manually.
    """
    if not scope_section:
        return [], []

    sub_matches = list(_H3_RE.finditer(scope_section))
    if not sub_matches:
        return [], []

    subs: dict[str, str] = {}
    for i, m in enumerate(sub_matches):
        heading = m.group(1).strip().lower()
        start = m.end()
        end = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(scope_section)
        subs[heading] = scope_section[start:end].strip()

    in_items = _parse_bullets(subs.get("in", ""))
    out_items = _parse_bullets(subs.get("out", ""))
    return in_items, out_items


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_task_file(content: str) -> ParsedTask | None:
    """Parse a task markdown file into a ParsedTask.

    Returns None if the file has no recognizable `# TASK-NNN: ...` H1,
    which is how callers should detect a non-task markdown that happened
    to be in the tasks/ directory (e.g. README).

    Args:
        content: Full file content as a string.

    Returns:
        Populated ParsedTask, or None if the file is not a task.
    """
    if not content or not content.strip():
        return None

    # 0. Extract Phase M routing fields from YAML frontmatter (before stripping)
    yaml_fields = _parse_yaml_frontmatter(content)

    # 1. Strip front-matter first so H1 detection isn't confused
    body = _strip_front_matter(content)

    # 2. Extract H1
    h1_match = _H1_RE.search(body)
    if h1_match is None:
        logger.debug("parse_task_file: no H1 found")
        return None

    task_id, domain, title = extract_task_id_from_h1(h1_match.group(1))
    if task_id is None:
        logger.debug("parse_task_file: H1 does not match TASK-### pattern")
        return None

    raw_title = h1_match.group(1).strip()

    # 3. Split into sections by H2
    sections = _split_sections(body)

    goal_text = _extract_first_paragraph(sections.get("goal", ""))
    scope_in, scope_out = _parse_scope(sections.get("scope", ""))
    requirements = _parse_numbered(sections.get("requirements", ""))
    dependencies = extract_dependencies(sections.get("dependencies", ""))
    source_of_truth = _parse_bullets(sections.get("source of truth", ""))
    read_first = _parse_bullets(sections.get("read first", ""))
    open_questions = sections.get("open questions", "").strip()
    rabbit_holes = sections.get("rabbit holes", "").strip()
    verification = sections.get("verification", "").strip()

    return ParsedTask(
        task_id=task_id,
        title=title,
        raw_title=raw_title,
        domain=domain,
        goal_text=goal_text,
        scope_in=scope_in,
        scope_out=scope_out,
        requirements=requirements,
        dependencies=dependencies,
        source_of_truth=source_of_truth,
        read_first=read_first,
        open_questions=open_questions,
        rabbit_holes=rabbit_holes,
        verification=verification,
        content_hash=_compute_content_hash(content),
        intensity=yaml_fields.get("intensity"),
        persona=yaml_fields.get("persona"),
        situation=yaml_fields.get("situation"),
    )
