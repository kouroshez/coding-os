"""Audit internal markdown links across docs/ for broken targets, anchors, and duplicates.

Also scans every repo-root *.md (README, CONTRIBUTING, SECURITY, …) and
flags symlinked directories inside the doc tree — a symlink dir resolves
transparently on a local filesystem but renders as a plain file on
GitHub, so every link that traverses it 404s in the web view. Link
targets resolve case-exactly: macOS's case-insensitive filesystem
accepts `Foo.md` for `foo.md`, but the same link 404s on GitHub/Linux.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO = Path(__file__).resolve().parent.parent.parent.parent
DOCS = (REPO / "docs").resolve()
# code-os-core-docs: external reference material (not project docs).
# _templates: doc TEMPLATES shipped by `cos init` — their links are
#   intentionally consumer-relative / placeholder (`relative/path`,
#   `./<related>.md`), so auditing them as navigable docs is a
#   category error.
SKIP_DIRS = {"code-os-core-docs", "_templates"}
# Repo-root markdown files (agent entrypoints + community files) —
# scanned for links but exempt from the doc frontmatter contract.
# Symlinks (CLAUDE.md → AGENTS.md) are skipped to avoid double-scanning.
ROOT_DOCS = sorted(p.name for p in REPO.glob("*.md") if not p.is_symlink())
# Categories that signal real breakage — non-zero exit when any are present.
_FAIL_CATEGORIES = {"BROKEN-FILE", "BROKEN-ANCHOR", "DEAD-NEXT-LINK", "SYMLINK-DIR"}

_LINK = re.compile(r"\[([^\]]*?)\]\(([^)]+?)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _blank(match: re.Match) -> str:
    """Replace a region with spaces, preserving newlines (so offsets hold)."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _exists_exact(path: Path) -> bool:
    """True when path exists with byte-exact casing on every segment.

    macOS's default case-insensitive filesystem lets `Foo.md` satisfy a
    link written `foo.md`; the same link 404s on GitHub and Linux CI, so
    a plain .exists() check structurally cannot catch it here.
    """
    if not path.exists():
        return False
    try:
        parts = path.resolve().relative_to(REPO).parts
    except ValueError:
        return True
    current = REPO
    for part in parts:
        try:
            if part not in os.listdir(current):
                return False
        except OSError:
            return True
        current = current / part
    return True


def _strip_for_links(text: str) -> str:
    """Blank fenced blocks, inline code, and HTML comments for LINK scans.

    Link patterns inside ```fences```, `inline code`, and
    <!-- comments --> are documentation ABOUT links — e.g. a doc that
    shows `[text](path)` as example syntax, or a Go snippet containing
    `F[T any](…)`. They are not real links and must not be audited.
    """
    text = _HTML_COMMENT.sub(_blank, text)
    text = _FENCE.sub(_blank, text)
    text = _INLINE_CODE.sub(_blank, text)
    return text


def _strip_for_headings(text: str) -> str:
    """Blank fenced blocks + HTML comments for HEADING/anchor scans.

    Unlike the link strip, inline code is KEPT: GitHub includes a
    heading's code-span content in the anchor slug — `## Rule 1 —
    Never hardcode `.claude/` in `core/`` anchors as
    `rule-1--never-hardcode-claude-in-core`. Only fenced blocks (where
    a `#` is not a real heading) and comments are removed.
    """
    text = _HTML_COMMENT.sub(_blank, text)
    text = _FENCE.sub(_blank, text)
    return text


_FRONTMATTER = re.compile(
    r"^<!--\s*domain:[A-Z_]+\s*\|\s*layer:[a-z_]+\s*\|\s*ssot:(?:true|false|ref)\s*\|\s*updated:(?:\d{4}-\d{2}-\d{2}|auto)\s*-->\s*$"
)
_OPENING_NEXT = re.compile(r"^(?:Read next:|>\s*N:)\s*(.+)$", re.M)


def _slugify(text: str) -> str:
    """Slugify a heading the way GitHub does.

    GitHub's anchor algorithm (github-slugger): lowercase, drop
    characters that are not word/space/hyphen, then replace each
    whitespace character with a single hyphen. Crucially it does NOT
    collapse consecutive hyphens — `## Rule 0 — Docs-first` becomes
    `rule-0--docs-first` (the em-dash is dropped, the two spaces around
    it become two hyphens). The previous implementation collapsed `-+`,
    which produced `rule-0-docs-first` and false-flagged every
    `Rule N — title` cross-reference as a broken anchor.
    """
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s", "-", s)
    return s or "section"


def _is_external(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme) and parsed.scheme not in {"file", ""}


def _gather_anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for match in _HEADING.finditer(text):
        slug = _slugify(match.group(2))
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return anchors


def _gather_md_files() -> list[Path]:
    files: list[Path] = []
    for path in DOCS.rglob("*.md"):
        rel = path.relative_to(DOCS)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    for name in ROOT_DOCS:
        root_doc = REPO / name
        if root_doc.is_file():
            files.append(root_doc)
    return sorted(files)


def _check_symlink_dirs() -> list[tuple[str, str]]:
    """Flag symlinked directories inside docs/.

    A symlink dir resolves transparently on the local filesystem, so
    link auditing that calls .resolve() never notices it. But GitHub
    (and most web doc viewers) render a symlink as a plain text file —
    so every link that traverses the symlink 404s in the browser. This
    is the exact failure mode that hid ~95 broken links behind a
    docs/governance + docs/workflow symlink pair.
    """
    findings: list[tuple[str, str]] = []
    for dirpath, dirnames, _files in os.walk(DOCS):
        for dirname in dirnames:
            full = Path(dirpath) / dirname
            if full.is_symlink():
                rel = full.relative_to(REPO)
                findings.append(
                    (
                        "SYMLINK-DIR",
                        f"{rel} is a symlink — GitHub renders it as a file; "
                        f"every link through it 404s. Replace with a real directory.",
                    )
                )
    return findings


def _check_links(path: Path, anchor_cache: dict[Path, set[str]]) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8")
    text = _strip_for_links(raw)
    findings: list[tuple[str, str]] = []
    rel = path.relative_to(REPO)

    # Frontmatter contract exemptions:
    #  - ROOT_DOCS (AGENTS.md): repo-root entrypoint, not docs/ taxonomy.
    #  - docs/tasks/: Scrumban task + audit files use YAML frontmatter
    #    (`---\nid: TASK-NNN\n...`), not the HTML-comment doc header.
    #  - docs/adr/: ADRs are Nygard-format records, a distinct genre.
    rel_parts = set(path.relative_to(REPO).parts) if path.is_relative_to(REPO) else set()
    frontmatter_exempt = path.name in ROOT_DOCS or "tasks" in rel_parts or "adr" in rel_parts
    if not frontmatter_exempt:
        first_line = raw.split("\n", 1)[0]
        if not _FRONTMATTER.match(first_line):
            findings.append(("BAD-FRONTMATTER", f"{rel}: {first_line[:100]!r}"))

    for match in _LINK.finditer(text):
        url = unquote(match.group(2).strip())
        if _is_external(url) or url.startswith(("mailto:", "javascript:")):
            continue
        if "#" in url:
            file_part, anchor = url.split("#", 1)
        else:
            file_part, anchor = url, None

        if file_part:
            target = (path.parent / file_part).resolve()
            if not _exists_exact(target):
                root_target = (REPO / file_part.lstrip("/")).resolve()
                if not _exists_exact(root_target):
                    findings.append(("BROKEN-FILE", f"{rel} -> {url}"))
                    continue
                target = root_target
        else:
            target = path

        if anchor and target.suffix == ".md":
            anchors = anchor_cache.get(target)
            if anchors is None:
                anchors = _gather_anchors(_strip_for_headings(target.read_text(encoding="utf-8")))
                anchor_cache[target] = anchors
            if anchor not in anchors:
                findings.append(("BROKEN-ANCHOR", f"{rel} -> {url}"))

    for match in _OPENING_NEXT.finditer(text):
        line = match.group(1)
        for inner in _LINK.finditer(line):
            target_url = unquote(inner.group(2).strip())
            if _is_external(target_url):
                continue
            file_part = target_url.split("#", 1)[0]
            if not file_part:
                continue
            target = (path.parent / file_part).resolve()
            if not target.exists():
                root_target = (REPO / file_part.lstrip("/")).resolve()
                if not root_target.exists():
                    findings.append(("DEAD-NEXT-LINK", f"{rel} -> Read next:{target_url}"))

    return findings


def _check_orphans() -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for index_path in DOCS.rglob("00-index.md"):
        rel = index_path.relative_to(DOCS)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        text = index_path.read_text(encoding="utf-8")
        listed: set[str] = set()
        for match in _LINK.finditer(text):
            url = match.group(2).strip()
            if _is_external(url) or "#" in url or url.startswith(".."):
                continue
            listed.add(url.lstrip("./"))
        for sibling in index_path.parent.glob("*.md"):
            if sibling.name == "00-index.md":
                continue
            if sibling.name not in listed:
                findings.append(("ORPHAN-FILE", f"{sibling.relative_to(REPO)} not listed in {rel}"))
    return findings


def _check_dup_h2() -> list[tuple[str, str]]:
    bucket: dict[str, list[str]] = defaultdict(list)
    generic = {
        "tl;dr",
        "why",
        "overview",
        "rollback",
        "anti-patterns",
        "acceptance",
        "steps",
        "scope",
        "notes",
        "references",
        "see also",
        "background",
        "summary",
        "links",
        "purpose",
        "examples",
        "verification",
        "the model",
        "the contract",
        "when to use",
        "when to invoke",
        "the seven checks",
        "the mental model",
        "steps to add a new adapter",
        "steps to modify an existing adapter",
    }
    for path in _gather_md_files():
        # ADRs (docs/adr/) are Nygard-format: every record repeats
        # Context / Decision / Consequences / Alternatives by design.
        # Counting those as duplicate H2s is a genre false positive.
        if "adr" in path.relative_to(REPO).parts:
            continue
        text = _strip_for_headings(path.read_text(encoding="utf-8"))
        for match in _HEADING.finditer(text):
            level = len(match.group(1))
            if level != 2:
                continue
            title = match.group(2).strip()
            if title.strip().lower().rstrip(".") in generic:
                continue
            bucket[title].append(str(path.relative_to(REPO)))
    findings: list[tuple[str, str]] = []
    for title, files in bucket.items():
        if len(files) >= 3:
            findings.append(("DUP-H2", f"'{title}' in {len(files)} files: {', '.join(files[:5])}"))
    return findings


def main() -> int:
    md_files = _gather_md_files()
    anchor_cache: dict[Path, set[str]] = {}
    findings: list[tuple[str, str]] = []
    for path in md_files:
        findings.extend(_check_links(path, anchor_cache))
    findings.extend(_check_symlink_dirs())
    findings.extend(_check_orphans())
    findings.extend(_check_dup_h2())

    by_cat: dict[str, list[str]] = defaultdict(list)
    for cat, msg in findings:
        by_cat[cat].append(msg)

    print(f"Scanned {len(md_files)} markdown files (skipping: {sorted(SKIP_DIRS)})\n")
    for cat in [
        "SYMLINK-DIR",
        "BROKEN-FILE",
        "BROKEN-ANCHOR",
        "DEAD-NEXT-LINK",
        "BAD-FRONTMATTER",
        "ORPHAN-FILE",
        "DUP-H2",
    ]:
        rows = by_cat.get(cat, [])
        print(f"== {cat} ({len(rows)}) ==")
        for row in sorted(rows):
            print(f"  {row}")
        print()

    total = sum(len(v) for v in by_cat.values())
    print(f"TOTAL findings: {total}")

    # Exit non-zero on real breakage (broken links/anchors). Warnings like
    # ORPHAN-FILE, BAD-FRONTMATTER, DUP-H2 do not fail the audit — they are
    # advisory categories the docs-lint suite tracks separately.
    fail_count = sum(len(by_cat.get(cat, [])) for cat in _FAIL_CATEGORIES)
    if fail_count > 0:
        print(f"FAIL: {fail_count} breaking findings in {sorted(_FAIL_CATEGORIES)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
