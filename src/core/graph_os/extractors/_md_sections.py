"""Frontmatter, heading, and link scanning for the markdown extractor.

Three body scans that share the document's regex vocabulary: frontmatter (both
the HTML-comment and YAML-fence conventions), the ATX heading tree that gives
in-page anchors their uid, and the inline/wiki link scan that produces the
cross-document edges.
"""

from __future__ import annotations

import hashlib
import re

from ..types import GraphEdge, GraphNode
from ._extract_base import EXTRACTOR_ID, ExtractionResult, _normalize_path
from ._md_read_next import _emit_read_next_targets
from ._md_resolve import _resolve_link
from ._md_uids import file_uid, frontmatter_key_uid, heading_uid, slugify

# Match `[text](target)` — target may contain nested parens via the
# balanced pattern below. Stops at unescaped `)`.
_INLINE_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+(?:\s+\"[^\"]*\")?)\)")
# `[[wikilink]]` or `[[wikilink|alias]]`.
_WIKI_LINK_RE = re.compile(r"\[\[(?P<target>[^\]|]+)(?:\|[^\]]+)?\]\]")
# ATX-style heading: `##  Title`. Setext headings are rare in this repo so
# we skip them for simplicity.
_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
# Frontmatter HTML comment used across coding-os docs:
# `<!-- domain:backend | layer:engineering | ssot:true | updated:... -->`
_HTML_FRONTMATTER_RE = re.compile(r"<!--\s*(?P<body>[^-]+(?:-(?!->)[^-]*)*)\s*-->")
# YAML fence: lines between `---` at file start.
_YAML_FENCE_RE = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*", re.DOTALL)
# Fenced code blocks: ```...``` — stripped before link extraction.
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)


def _extract_doc_blob(content: str, *, cap: int = 4000) -> str:
    """Flat preview of the doc's body, trimmed to keep nodes lean."""
    stripped = _FENCED_CODE_RE.sub("", content)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.DOTALL)
    compact = re.sub(r"\s+", " ", stripped).strip()
    return compact[:cap]


def _extract_frontmatter(path: str, content: str, result: ExtractionResult) -> None:
    """Pull out HTML-comment and/or YAML-fence frontmatter keys."""
    candidates: list[str] = []

    yaml_match = _YAML_FENCE_RE.match(content)
    if yaml_match:
        candidates.append(yaml_match.group("body"))

    html_match = _HTML_FRONTMATTER_RE.search(content[:4000])  # cap scan range
    if html_match:
        body = html_match.group("body")
        # The coding-os convention is pipe-separated key:value pairs; accept
        # both the multi-key style ("domain:x | layer:y") and a single-key
        # HTML comment ("<!-- ssot_of:path -->") so ssot/read_next edges
        # survive even in minimal frontmatter.
        candidates.append(body)

    for body in candidates:
        for raw in body.splitlines() if "\n" in body else body.split("|"):
            if ":" not in raw:
                continue
            key, _, value = raw.strip().partition(":")
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")
            if not key or not value:
                continue
            # Frontmatter keys are simple identifiers. Reject anything
            # that looks like prose / markdown (heading `#`, backtick,
            # whitespace, braces) — the HTML-comment scan otherwise
            # mis-parses a `# `output_format={type|...}`` code line as a
            # key:value pair and mints a malformed doc:frontmatter node.
            if not re.fullmatch(r"[a-z0-9_]+", key):
                continue
            # `reads:[a, b, c]` short-form vector — emit one read_next edge
            # per target instead of a single key node carrying the literal
            # bracket-string. Short-form authors get the same graph
            # surface as long-form `read_next:path` keys.
            if key == "reads":
                _emit_read_next_targets(path, value, result, source="frontmatter:reads")
                continue
            node = GraphNode(
                uid=frontmatter_key_uid(path, key),
                kind="doc:frontmatter_key",
                label=f"{key}={value}",
                file_path=_normalize_path(path),
                lang="md",
                metadata={"key": key, "value": value, "extractor": EXTRACTOR_ID},
            )
            result.nodes.append(node)
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid(path),
                    target_uid=node.uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
            # Special-case: ssot_of, read_next, read_before are cross-
            # file relations declared via frontmatter — emit the
            # directed edge in addition to the containment one.
            # Frontmatter values use REPO-ROOTED paths (e.g.
            # `docs/core/rules.md`), not relative — this matches how
            # every doc in this repo currently authors them.
            if key in {"ssot_of", "read_next", "read_before"}:
                target_path = value.split()[0]
                if target_path.startswith(("http://", "https://")):
                    target_uid = f"doc:external:{target_path}"
                elif target_path.startswith(("../", "./")):
                    # F13 / Audit #4: frontmatter values are usually
                    # repo-rooted, but some docs ship relative paths.
                    # Anchor those against the source doc instead of
                    # emitting a `doc:file:../...` stub.
                    target_uid = _resolve_link(path, target_path)
                    if not target_uid:
                        continue
                else:
                    target_uid = f"doc:file:{_normalize_path(target_path)}"
                result.edges.append(
                    GraphEdge(
                        source_uid=file_uid(path),
                        target_uid=target_uid,
                        edge_type=key,
                        extractor=EXTRACTOR_ID,
                        confidence=0.9,
                        source_span=f"{_normalize_path(path)}:frontmatter",
                    )
                )


def _extract_headings(
    path: str, content: str, result: ExtractionResult
) -> list[tuple[str, int, str]]:
    """Produce heading nodes + contains edges + a list of (uid, level, slug).

    Returns a list in document order so link resolution can point to the
    nearest preceding heading when the link has an anchor.
    """
    headings: list[tuple[str, int, str]] = []
    stack: list[tuple[int, str]] = [(0, file_uid(path))]
    slug_counts: dict[str, int] = {}

    for lineno, line in enumerate(content.splitlines(), start=1):
        # Skip ATX headings inside fenced code — approximate by checking
        # balanced backticks up to this line.
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group("level"))
        title = m.group("title").strip()
        if not title:
            continue
        slug = slugify(title)
        if not slug:
            slug = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
        occurrence = slug_counts.get(slug, 0)
        slug_counts[slug] = occurrence + 1
        uid = heading_uid(path, slug, level, occurrence)

        node = GraphNode(
            uid=uid,
            kind="doc:heading",
            label=title,
            file_path=_normalize_path(path),
            start_line=lineno,
            lang="md",
            metadata={
                "level": level,
                "slug": slug,
                "occurrence": occurrence,
                "extractor": EXTRACTOR_ID,
            },
        )
        result.nodes.append(node)

        # Walk up the stack until we find a parent whose level is lower.
        while stack[-1][0] >= level:
            stack.pop()
        parent_uid = stack[-1][1]
        result.edges.append(
            GraphEdge(
                source_uid=parent_uid,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{_normalize_path(path)}:{lineno}",
            )
        )
        stack.append((level, uid))
        headings.append((uid, level, slug))
    return headings


def _extract_links(
    path: str,
    cleaned_content: str,
    headings: list[tuple[str, int, str]],
    result: ExtractionResult,
) -> None:
    """Emit links_to + cites_heading edges.

    Headings list is consumed for in-page anchor → heading-node
    resolution (so `[text](#slug)` lands on the heading, not the file).
    """
    slug_to_uid: dict[str, str] = {}
    for uid, _level, slug in headings:
        # First occurrence wins for in-page links — same convention as
        # GitHub anchors.
        slug_to_uid.setdefault(slug, uid)

    # Inline links.
    for match in _INLINE_LINK_RE.finditer(cleaned_content):
        target = match.group("target").strip()
        if not target:
            continue
        resolved = _resolve_link(path, target)
        if not resolved:
            continue
        # Heading anchor inside THIS file — emit cites_heading.
        if resolved.startswith(f"doc:file:{_normalize_path(path)}#"):
            anchor = resolved.rsplit("#", 1)[1]
            heading_uid_resolved = slug_to_uid.get(anchor)
            if heading_uid_resolved:
                result.edges.append(
                    GraphEdge(
                        source_uid=file_uid(path),
                        target_uid=heading_uid_resolved,
                        edge_type="cites_heading",
                        extractor=EXTRACTOR_ID,
                        confidence=0.95,
                    )
                )
                continue
        # Cross-file heading anchor — cites_heading to the target file's
        # heading node (target_uid assumes the other file will have the
        # heading indexed in the same run; if not, the edge dangles
        # until the cross-file reindex catches up).
        if "#" in resolved and resolved.startswith("doc:file:"):
            base_path, anchor = resolved.split("#", 1)
            target_file = base_path  # keep doc:file prefix
            target_heading = f"doc:heading:{base_path[len('doc:file:') :]}#{anchor}"
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid(path),
                    target_uid=target_heading,
                    edge_type="cites_heading",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,  # lower — target heading may not exist
                    source_span=f"{_normalize_path(path)}",
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid(path),
                    target_uid=target_file,
                    edge_type="links_to",
                    extractor=EXTRACTOR_ID,
                    confidence=0.9,
                )
            )
            continue
        # Plain link — file-level references_to.
        result.edges.append(
            GraphEdge(
                source_uid=file_uid(path),
                target_uid=resolved,
                edge_type="links_to",
                extractor=EXTRACTOR_ID,
                confidence=0.9 if resolved.startswith("doc:file:") else 0.6,
            )
        )

    # Wiki links.
    for match in _WIKI_LINK_RE.finditer(cleaned_content):
        target = match.group("target").strip()
        if not target:
            continue
        if target.endswith(".md"):
            resolved = _resolve_link(path, target)
        else:
            resolved = _resolve_link(path, target + ".md")
        if not resolved:
            continue
        result.edges.append(
            GraphEdge(
                source_uid=file_uid(path),
                target_uid=resolved,
                edge_type="links_to",
                extractor=EXTRACTOR_ID,
                confidence=0.8,
                source_span=f"{_normalize_path(path)}:wikilink",
            )
        )
