"""Regenerate `<file>.INDEX.md` sidecar for a fat markdown doc.

PURPOSE:      Build intra-file navigation index from H1/H2/H3 headings so
              agents read only the section they need (≈300-800 tokens) via
              `cos_doc_section` instead of full-reading the doc (≥5k tokens).
              Spec: docs/engineering/section-index.md.
INPUT:        argv[1] — path to the source `.md` file.
              flags  — `--dry-run` prints to stdout, `--force` skips threshold
                       check, `--all <root>` walks every fat doc under root.
OUTPUT:       Writes `<file>.INDEX.md` next to the source. Prints `OK:` /
              `WARN:` / `SKIP:` per AGENTS.md script convention.
DEPENDENCIES: stdlib only — must run with the agent's `python3` without
              installing anything (PostToolUse hook constraint).
NOTES:        Slugs follow GitHub-flavored markdown: ASCII-lower, spaces
              -> "-", strip punctuation except "-", collision suffix "-2".
              Slug stability is the contract — line ranges drift, slugs do
              not unless the heading text is renamed. Token estimate uses
              `len(text)//4`, matching `core/thinking_os/tools/_shared.ok()`.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BEGIN_MARKER = "<!-- BEGIN auto-section-index -->"
END_MARKER = "<!-- END auto-section-index -->"

LINE_THRESHOLD = 400
TOKEN_THRESHOLD = 5_000
GIANT_SECTION_LINES = 500

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_FRONTMATTER_FENCE = re.compile(r"^---\s*$")
_HTML_FRONTMATTER = re.compile(r"^<!--\s*(.+?)\s*-->\s*$")
_CODE_FENCE = re.compile(r"^```")

_STOPLIST = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "into", "are",
    "but", "not", "all", "any", "can", "has", "have", "was", "were", "use",
    "used", "uses", "via", "per", "let", "lets", "set", "get", "gets",
    "see", "etc", "its", "their", "they", "them", "you", "your", "our",
    "one", "two", "three", "first", "next", "also", "then", "than", "such",
    "more", "most", "less", "very", "much", "many", "some", "few", "each",
    "every", "only", "still", "yet", "always", "never", "now", "new", "old",
    "non", "yes", "do", "does", "did", "be", "is", "as", "in", "on", "at",
    "to", "of", "by", "or", "if", "an", "we", "it", "so", "up", "out", "off",
    "over", "under", "above", "below", "when", "where", "while", "until",
    "since", "before", "after", "between", "among", "without", "within",
    "during", "across", "through", "though", "although", "however", "else",
    "either", "neither",
})


def _slugify(text: str, taken: set[str]) -> str:
    """GitHub-flavored slug with collision counter."""
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    if not s:
        s = "section"
    base = s
    i = 2
    while s in taken:
        s = f"{base}-{i}"
        i += 1
    taken.add(s)
    return s


def _strip_html_inline(line: str) -> str:
    line = re.sub(r"<[^>]+>", "", line)
    line = re.sub(r"`([^`]+)`", r"\1", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    return line.strip()


def _parse_headings(lines: list[str]) -> list[dict]:
    """Walk lines, return headings with start lines (1-indexed).

    Skips fenced code blocks and frontmatter at file head so a `# foo`
    inside a triple-backtick block is never confused with a real heading.
    """
    headings: list[dict] = []
    in_fence = False
    in_frontmatter = False
    fm_lines_seen = 0

    for idx, raw in enumerate(lines, start=1):
        if idx == 1 and _FRONTMATTER_FENCE.match(raw):
            in_frontmatter = True
            continue
        if in_frontmatter:
            fm_lines_seen += 1
            if _FRONTMATTER_FENCE.match(raw):
                in_frontmatter = False
            if fm_lines_seen > 50:
                in_frontmatter = False
            continue

        if _CODE_FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        m = _HEADING_RE.match(raw)
        if not m:
            continue
        level = len(m.group(1))
        title = _strip_html_inline(m.group(2))
        if not title:
            continue
        headings.append({"level": level, "title": title, "start": idx})
    return headings


def _assign_ranges(headings: list[dict], total_lines: int) -> None:
    """In-place: each section ends at next heading - 1; last ends at EOF."""
    for i, h in enumerate(headings):
        if i + 1 < len(headings):
            h["end"] = headings[i + 1]["start"] - 1
        else:
            h["end"] = total_lines
        h["lines"] = max(0, h["end"] - h["start"] + 1)


def _section_text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1:end])


def _token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


def _section_keywords(text: str, heading_words: set[str], top: int = 3) -> list[str]:
    """Top-N words by frequency, excluding stoplist + heading words."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
    counts = Counter(
        w for w in words
        if w not in _STOPLIST and w not in heading_words and len(w) > 2
    )
    return [w for w, _ in counts.most_common(top)]


def _parse_frontmatter(lines: list[str]) -> dict:
    """Return YAML-ish frontmatter as flat dict (best-effort, no PyYAML)."""
    if not lines:
        return {}
    if _FRONTMATTER_FENCE.match(lines[0]):
        fm: dict = {}
        for line in lines[1:]:
            if _FRONTMATTER_FENCE.match(line):
                break
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip("\"'")
        return fm
    if (m := _HTML_FRONTMATTER.match(lines[0])):
        out: dict = {}
        for chunk in m.group(1).split("|"):
            if ":" in chunk:
                k, v = chunk.split(":", 1)
                out[k.strip()] = v.strip()
        return out
    return {}


def _qualifies(line_count: int, token_count: int, fm: dict, force: bool) -> bool:
    if force:
        return True
    if str(fm.get("force_index", "")).lower() == "true":
        return True
    if str(fm.get("no_index", "")).lower() == "true":
        return False
    return line_count >= LINE_THRESHOLD or token_count >= TOKEN_THRESHOLD


def _render_index(
    source: Path,
    lines: list[str],
    headings: list[dict],
    fm: dict,
) -> str:
    """Build INDEX.md body with stable frontmatter + auto-section fence."""
    domain = fm.get("domain", "DOCS")
    today = date.today().isoformat()
    total_lines = len(lines)
    total_tokens = _token_estimate("\n".join(lines))

    taken: set[str] = set()
    for h in headings:
        h["slug"] = _slugify(h["title"], taken)
        body = _section_text(lines, h["start"], h["end"])
        h["tokens"] = _token_estimate(body)
        heading_words = {w for w in re.findall(r"[a-z]+", h["title"].lower())}
        h["keywords"] = _section_keywords(body, heading_words)

    out: list[str] = [
        f"<!-- domain:{domain} | layer:index | ssot:ref | updated:{today} | parent:{source.name} -->",
        f"# {source.name} — Section Index",
        "",
        f"> Source: `{source.name}` ({total_lines} lines, ≈{total_tokens} tokens).",
        "> Read the section you need via `cos_doc_section(path, slug)` or `Read(path, offset, limit)`.",
        "> Slug is stable across edits; line range refreshes on every Write/Edit (debounced 5s).",
        "",
    ]
    out.append(BEGIN_MARKER)
    out.append(f"<!-- generated by scripts/regen_section_index.py on {today} -->")
    out.append("")
    out.append("## Sections")
    out.append("")
    out.append("| Lvl | Title | Slug | Start | End | Lines | ≈Tokens |")
    out.append("|-----|-------|------|------:|----:|------:|--------:|")
    for h in headings:
        title_safe = h["title"].replace("|", "\\|")
        out.append(
            f"| H{h['level']} | {title_safe} | `{h['slug']}` | "
            f"{h['start']} | {h['end']} | {h['lines']} | {h['tokens']} |"
        )

    kw_lines: list[str] = []
    for h in headings:
        if h["keywords"]:
            kw_lines.append(
                f"- {' / '.join(h['keywords'])} → §`{h['slug']}` ({h['title']})"
            )
    if kw_lines:
        out.append("")
        out.append("## Keyword → Section")
        out.append("")
        out.extend(kw_lines)

    giants = [h for h in headings if h["lines"] >= GIANT_SECTION_LINES]
    if giants:
        out.append("")
        out.append("## Giant sections (grep first, do not full-read)")
        out.append("")
        for h in giants:
            out.append(
                f"> ⚠️ `{h['slug']}` ({h['start']}–{h['end']}, {h['lines']} lines, "
                f"≈{h['tokens']} tokens). Use `Grep(pattern, path)` then read ±50 lines."
            )

    out.append("")
    out.append(END_MARKER)
    out.append("")
    return "\n".join(out)


def _splice(existing: str, regenerated: str) -> str:
    """Replace the auto-section fence; keep prose outside the fence intact."""
    if BEGIN_MARKER not in existing or END_MARKER not in existing:
        return regenerated
    pre = existing.split(BEGIN_MARKER, 1)[0]
    post = existing.split(END_MARKER, 1)[1]
    new_fenced = regenerated.split(BEGIN_MARKER, 1)[1].split(END_MARKER, 1)[0]
    return f"{pre}{BEGIN_MARKER}{new_fenced}{END_MARKER}{post}"


def regenerate(source: Path, *, write: bool = True, force: bool = False) -> str | None:
    """Regenerate `<source>.INDEX.md`. Returns new body or None on skip.

    Skip cases (None return):
        - source not a `.md` file
        - source is itself an INDEX/00-index file
        - source below threshold (and force=False, no force_index frontmatter)
        - no parseable headings (empty doc / pure prose without H1-H3)
    """
    if not source.exists() or not source.is_file():
        return None
    if source.suffix.lower() != ".md":
        return None
    name = source.name
    if name.endswith(".INDEX.md") or name == "00-index.md":
        return None

    raw = source.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    fm = _parse_frontmatter(lines)
    line_count = len(lines)
    token_count = _token_estimate(raw)
    if not _qualifies(line_count, token_count, fm, force):
        return None
    headings = _parse_headings(lines)
    if not headings:
        return None
    _assign_ranges(headings, line_count)

    body = _render_index(source, lines, headings, fm)
    target = source.with_name(source.stem + ".INDEX.md")
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        body = _splice(existing, body)
    if write:
        target.write_text(body, encoding="utf-8")
    return body


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", help="Source .md file (or root with --all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print regenerated INDEX instead of writing")
    parser.add_argument("--force", action="store_true",
                        help="Bypass threshold (always generate)")
    parser.add_argument("--all", action="store_true",
                        help="Walk all .md files under `path`")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if args.all:
        if not root.is_dir():
            print(f"ERROR: --all needs a directory, got {root}", file=sys.stderr)
            return 1
        targets = sorted(
            p for p in root.rglob("*.md")
            if not p.name.endswith(".INDEX.md")
            and p.name != "00-index.md"
        )
    else:
        targets = [root]

    written = skipped = 0
    for src in targets:
        body = regenerate(src, write=not args.dry_run, force=args.force)
        if body is None:
            print(f"SKIP: {src} (below threshold or no headings)")
            skipped += 1
            continue
        if args.dry_run:
            print(f"--- {src.with_name(src.stem + '.INDEX.md')} ---")
            print(body)
        else:
            print(f"OK: regenerated {src.with_name(src.stem + '.INDEX.md')}")
        written += 1
    print(f"INFO: {written} written, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
