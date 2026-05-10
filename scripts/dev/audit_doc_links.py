"""Audit internal markdown links across docs/ for broken targets, anchors, and duplicates."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = REPO / "docs"
SKIP_DIRS = {"code-os-core-docs"}

_LINK = re.compile(r"\[([^\]]*?)\]\(([^)]+?)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
_FRONTMATTER = re.compile(
    r"^<!--\s*domain:[A-Z_]+\s*\|\s*layer:[a-z_]+\s*\|\s*ssot:(?:true|false|ref)\s*\|\s*updated:(?:\d{4}-\d{2}-\d{2}|auto)\s*-->\s*$"
)
_OPENING_NEXT = re.compile(r"^(?:Read next:|>\s*N:)\s*(.+)$", re.M)


def _slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
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
    return sorted(files)


def _check_links(path: Path, anchor_cache: dict[Path, set[str]]) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    findings: list[tuple[str, str]] = []
    rel = path.relative_to(REPO)

    first_line = text.split("\n", 1)[0]
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
            if not target.exists():
                root_target = (REPO / file_part.lstrip("/")).resolve()
                if not root_target.exists():
                    findings.append(("BROKEN-FILE", f"{rel} -> {url}"))
                    continue
                target = root_target
        else:
            target = path

        if anchor and target.suffix == ".md":
            anchors = anchor_cache.get(target)
            if anchors is None:
                anchors = _gather_anchors(target.read_text(encoding="utf-8"))
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
                findings.append(
                    ("ORPHAN-FILE", f"{sibling.relative_to(REPO)} not listed in {rel}")
                )
    return findings


def _check_dup_h2() -> list[tuple[str, str]]:
    bucket: dict[str, list[str]] = defaultdict(list)
    generic = {
        "tl;dr", "why", "overview", "rollback", "anti-patterns",
        "acceptance", "steps", "scope", "notes", "references", "see also",
        "background", "summary", "links", "purpose", "examples",
        "verification", "the model", "the contract", "when to use",
        "when to invoke", "the seven checks", "the mental model",
        "steps to add a new adapter", "steps to modify an existing adapter",
    }
    for path in _gather_md_files():
        text = path.read_text(encoding="utf-8")
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
            findings.append(
                ("DUP-H2", f"'{title}' in {len(files)} files: {', '.join(files[:5])}")
            )
    return findings


def main() -> int:
    md_files = _gather_md_files()
    anchor_cache: dict[Path, set[str]] = {}
    findings: list[tuple[str, str]] = []
    for path in md_files:
        findings.extend(_check_links(path, anchor_cache))
    findings.extend(_check_orphans())
    findings.extend(_check_dup_h2())

    by_cat: dict[str, list[str]] = defaultdict(list)
    for cat, msg in findings:
        by_cat[cat].append(msg)

    print(f"Scanned {len(md_files)} markdown files (skipping: {sorted(SKIP_DIRS)})\n")
    for cat in [
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
