"""graph_os — markdown link + heading + frontmatter extractor (I.2).

DEPENDS:  stdlib regex; frontmatter is parsed from the HTML comment or
          YAML-fence convention used across coding-os docs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..types import GraphEdge, GraphNode

logger = logging.getLogger("graph_os.extractors.md_links")

EXTRACTOR_ID = "md_links@v1"

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

# Opening-block "Read next:" lines (TASK-156). Long form lives plain in the
# body; short form lives inside a blockquote (`> N: …`). Both produce
# read_next edges to every comma-separated target.
_OPENING_READ_NEXT_RE = re.compile(
    r"^(?:Read next:|>\s*N:)\s*(?P<targets>.+?)\s*$",
    re.MULTILINE,
)

# Strip markdown link wrapper `[label](href)` to keep only the href.
_LINK_HREF_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

# W6.5 (X7): valid path target must match this — no spaces, must look like
# a path / URL / fragment. Rejects garbage prose fragments captured by
# the previous lenient `_split_read_targets` (Round 3 root cause of 386
# stale_paths + ranking pollution from doc:file:"…prose…" uids).
_PATH_LIKE_RE = re.compile(r"^[\w./\-:#?&=%~+]+$")


def _split_read_targets(raw: str) -> list[str]:
    """Split a comma-or-bracket list of read_next targets into clean paths."""
    text = raw.strip()
    # Only collapse the wrapping brackets when the whole value is `[…]` —
    # short-form `reads:[a, b]`. Markdown links like `[a](a.md), [b](b.md)`
    # must keep their `[`/`]` so the link regex can still match.
    if text.startswith("[") and text.endswith("]") and "](" not in text:
        text = text[1:-1]
    if not text:
        return []
    fragments = [frag.strip() for frag in text.split(",") if frag.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for frag in fragments:
        match = _LINK_HREF_RE.search(frag)
        href = (match.group(1) if match else frag).strip()
        href = href.strip("`").strip()
        if not href or href in seen:
            continue
        # W6.5 (X7): reject prose fragments — only accept path-like strings.
        # Prevents `Relevant ADR in ../architecture/adr/ or the domain doc.`
        # from becoming a doc:file: uid.
        if not _PATH_LIKE_RE.match(href):
            continue
        seen.add(href)
        out.append(href)
    return out


# Repo-root prefixes — a read_next target starting with one of these is
# already repo-rooted and used verbatim; anything else (bare filename or
# `./`/`../`) is resolved against the source doc's directory.
_REPO_ROOT_PREFIXES = ("docs/", "src/", "tests/", "infrastructure/", "scripts/")


def _resolve_read_target(path: str, target_path: str) -> str | None:
    """Resolve a read_next / opening-block target to a clean uid.

    Bare filenames + `./`/`../` paths anchor against the source doc dir
    (R4 follow-up: a bare `accessibility-checklist.md` used to mint a
    repo-root `doc:file:accessibility-checklist.md` stub that never
    existed). Repo-rooted `docs/...`/`src/...` targets pass through.
    """
    if target_path.startswith(("http://", "https://")):
        return f"doc:external:{target_path}"
    if target_path.startswith(("../", "./")):
        resolved = _resolve_link(path, target_path)
        return resolved or None
    if target_path.startswith(_REPO_ROOT_PREFIXES):
        return f"doc:file:{_normalize_path(target_path)}"
    # Bare relative name — anchor against the source doc's directory.
    resolved = _resolve_link(path, target_path)
    return resolved or None


def _emit_read_next_targets(
    path: str,
    raw_value: str,
    result: ExtractionResult,
    *,
    source: str,
) -> None:
    """Emit one ``read_next`` edge per parsed target in ``raw_value``."""
    for target_path in _split_read_targets(raw_value):
        target_uid = _resolve_read_target(path, target_path)
        if not target_uid:
            continue
        result.edges.append(
            GraphEdge(
                source_uid=file_uid(path),
                target_uid=target_uid,
                edge_type="read_next",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                source_span=f"{_normalize_path(path)}:{source}",
            )
        )


def _extract_opening_block_reads(path: str, content: str, result: ExtractionResult) -> None:
    """Parse opening-block ``Read next:`` (long) and ``> N:`` (short)."""
    seen_targets: set[str] = set()
    for match in _OPENING_READ_NEXT_RE.finditer(content):
        for target_path in _split_read_targets(match.group("targets")):
            if target_path in seen_targets:
                continue
            seen_targets.add(target_path)
            target_uid = _resolve_read_target(path, target_path)
            if not target_uid:
                continue
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid(path),
                    target_uid=target_uid,
                    edge_type="read_next",
                    extractor=EXTRACTOR_ID,
                    confidence=0.9,
                    source_span=f"{_normalize_path(path)}:opening-block",
                )
            )


@dataclass(frozen=True)
class ParseError:
    """Non-fatal extractor warning (e.g. malformed frontmatter)."""

    kind: str
    detail: str
    line: int | None = None


@dataclass
class ExtractionResult:
    """Nodes, edges, parse_errors returned from extract()."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    parse_errors: list[ParseError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Slug / uid helpers
# ---------------------------------------------------------------------------


def slugify(heading: str) -> str:
    """Compute a stable URL-anchor slug from a heading title.

    Rules match GitHub-flavored Markdown: lowercase, strip non-alnum,
    collapse dashes. Deterministic — same input → same slug across
    platforms and runs (required by the P-I-11 determinism principle).
    """
    lowered = heading.lower()
    cleaned = re.sub(r"[^\w\s-]", "", lowered)
    return re.sub(r"[\s_]+", "-", cleaned).strip("-")


def file_uid(path: str) -> str:
    return f"doc:file:{_normalize_path(path)}"


def heading_uid(path: str, slug: str, level: int, occurrence: int) -> str:
    # occurrence disambiguates repeated headings under different parents.
    suffix = f":{occurrence}" if occurrence > 0 else ""
    return f"doc:heading:{_normalize_path(path)}#{slug}:{level}{suffix}"


def frontmatter_key_uid(path: str, key: str) -> str:
    return f"doc:frontmatter:{_normalize_path(path)}::{key}"


def _normalize_path(path: str) -> str:
    """Forward-slash, no trailing slash — stable across platforms."""
    return str(PurePosixPath(path.replace("\\", "/")))


def _classify_governance_path(normalised: str) -> tuple[str | None, str | None]:
    parts = normalised.split("/")
    if len(parts) >= 4 and parts[-1] == "SKILL.md" and "skills" in parts:
        skills_idx = parts.index("skills")
        if skills_idx + 1 < len(parts) - 1:
            return ("cos:skill", parts[skills_idx + 1])
    if (
        len(parts) >= 3
        and parts[-1].endswith(".md")
        and "rules" in parts
        and parts[-1] != "SKILL.md"
    ):
        rules_idx = parts.index("rules")
        if rules_idx + 1 == len(parts) - 1:
            return ("cos:rule", parts[-1][:-3])
    return (None, None)


_ASSET_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".pdf", ".mp4", ".mov", ".webm", ".mp3", ".woff", ".woff2", ".ttf", ".eot", ".zip",
})


def _resolve_link(origin_path: str, target: str) -> str:
    """Resolve a link (possibly relative) to an absolute repo-rooted path.

    Returns the target as a doc:file uid when it points to a filesystem
    path, or a canonical external URL for http(s) links.
    """
    target = target.strip()
    if target.startswith(("http://", "https://", "mailto:")):
        return f"doc:external:{target}"
    # W6.5 (X7) residual: reject targets carrying regex / markup
    # metacharacters — a prose regex like `[module](?P<module>[^'"]+)`
    # matches the inline-link regex and used to mint a garbage
    # `doc:file:?P<module>...` stub. Real paths never contain these.
    if any(c in target for c in "<>\"'{}^*|`"):
        return ""
    # Discard `"title"` suffix after a space.
    target = target.split(" ")[0]
    # Split off `#anchor`.
    path_part, _, anchor = target.partition("#")
    # If the link is to the same file's anchor only, resolve to self.
    if path_part == "":
        return f"doc:file:{_normalize_path(origin_path)}#{anchor}" if anchor else ""
    origin_dir = PurePosixPath(_normalize_path(origin_path)).parent
    resolved = (origin_dir / path_part).as_posix()
    # Collapse `./` and `../` — PurePosixPath already handles this in
    # most cases; normalise for Windows-style edge cases.
    parts: list[str] = []
    for part in resolved.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    normalised = "/".join(parts)
    # Repo-root fallback (F17): a doc nested deep in the meta-repo can
    # author a consumer-relative link (`../../docs/x`) that collapses to a
    # nonexistent `src/docs/x` here while the real file is `docs/x` at repo
    # root. If the collapsed path is missing but a repo-rooted variant of
    # the raw target exists, prefer the real file. Mirrors the bare-name
    # anchoring in _resolve_read_target; kills the stale_paths churn that
    # doctor --fix can only paper over.
    if normalised and not Path(normalised).exists():
        bare = path_part.lstrip("./")
        if bare and bare != normalised and Path(bare).is_file():
            normalised = bare
    # Markdown links can target any artefact in the repo; route them to
    # the right uid namespace by extension so a `.md → .py` link does
    # not create a ghost `doc:file` stub that duplicates the real
    # `code:file` node the code extractors emit.
    suffix = PurePosixPath(normalised).suffix.lower()
    # Image / binary asset links are not code or doc references — drop them
    # so a relative `![x](diagram.png)` never mints a code:file node.
    if suffix in _ASSET_SUFFIXES:
        return ""
    if suffix == "" and normalised and Path(normalised).is_dir():
        # Directory target → existing folder node, not a phantom doc:file:<dir>.
        return f"folder:{normalised}"
    if suffix == "" and not Path(normalised).is_file():
        # Extensionless target that is neither a real dir nor a real file is a
        # placeholder / prose fragment ('relative/path', 'docs/_meta/path',
        # unicode-ellipsis truncations) — minting a node for it created
        # permanent stale/orphan junk invisible to the doctor (TASK-056 B2).
        return ""
    if suffix in {".md", ".mdx", ""}:
        base = f"doc:file:{normalised}"
    elif normalised.startswith("docs/tasks/"):
        base = f"task:file:{normalised}"
    else:
        # Code-file nodes carry no line/heading anchor (the uid scheme has no
        # line numbers): a `foo.py#L954` link resolves to the file node, not a
        # phantom `code:file:...#L954` that pollutes similarity (TASK-056 B1).
        return f"code:file:{normalised}"
    return f"{base}#{anchor}" if anchor else base


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def extract(
    path: str,
    content: str,
) -> ExtractionResult:
    """Parse a Markdown document → nodes + edges."""
    result = ExtractionResult()
    try:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        normalised = _normalize_path(path)
        special_kind, special_label = _classify_governance_path(normalised)

        file_node = GraphNode(
            uid=file_uid(path),
            kind=special_kind or "doc:file",
            label=special_label or PurePosixPath(normalised).name,
            file_path=normalised,
            lang="md",
            doc_blob=_extract_doc_blob(content),
            content_hash=content_hash,
            metadata={"extractor": EXTRACTOR_ID},
        )
        result.nodes.append(file_node)

        # Frontmatter FIRST so linked docs get ssot/read_next edges even
        # when headings / body parsing fails later.
        _extract_frontmatter(path, content, result)

        # Opening-block "Read next:" / "> N:" → read_next edges. Runs after
        # frontmatter so duplicate-href dedupe inside the scan only fires
        # within the body. Frontmatter `reads:[…]` is handled inline via
        # `_emit_read_next_targets` to keep both forms graph-symmetric.
        # Strip fenced code first — TASK-162 fix #4 — so a `Read next:` line
        # that lives inside a ```bash``` block does not produce a false edge.
        _opening_block_content = _FENCED_CODE_RE.sub("", content)
        _extract_opening_block_reads(path, _opening_block_content, result)

        # Heading scan builds the containment tree AND a slug→uid map
        # for subsequent in-page fragment resolution.
        headings = _extract_headings(path, content, result)

        # Strip fenced code before link scan so ``[x](y)`` inside a code
        # block does not produce a false edge.
        cleaned = _FENCED_CODE_RE.sub("", content)
        _extract_links(path, cleaned, headings, result)

        # S3: attach Folder→...→File spine so the SPA tree-view always
        # has a connected root. Idempotent on uid — parallel extractors
        # emit identical folder uids and bulk_upsert de-dupes.
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )

        # Promote any edge-only uid (link target the extractor does not
        # own the source for) into a stub node so the backend's edge
        # write does not raise ValueError for unknown uids. Upserting
        # the extracted nodes in another pass will replace the stub
        # with the real row — uid is the join key.
        _promote_stubs(result)

        return result
    except Exception as exc:
        logger.debug("md_links.extract(%s) fatal error: %s", path, exc)
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def folder_uid(path: str) -> str:
    """Stable uid for a repo-rooted folder.

    Empty / ``.`` / ``/`` path collapse to the synthetic repo root uid.
    Matches the convention used by the backend's bulk_upsert — so
    parallel extractors emit the SAME uid for the same folder and the
    upsert de-duplicates.
    """
    normalised = _normalize_path(path)
    if normalised in ("", ".", "/"):
        return "folder:."
    return f"folder:{normalised}"


def emit_contains_spine(
    *,
    file_path: str,
    file_uid_: str,
    result: ExtractionResult,
    extractor_id: str,
) -> None:
    """Append folder nodes + Folder→Folder → Folder→File ``contains`` edges."""
    normalised = _normalize_path(file_path)
    if not normalised or normalised in (".", "/"):
        return

    # Walk up the directory chain → list of (uid, label, parent_uid).
    parts = [p for p in normalised.split("/") if p]
    if not parts:
        return
    # Drop the filename — we only want directory segments.
    directory_parts = parts[:-1]

    # Always emit the repo root folder (parent of every top-level dir).
    # uid stays `folder:.` for stability across rebuilds and idempotency;
    # `label` upgraded from "." to "repo-root" so the graph canvas shows
    # a recognisable anchor instead of a tiny dot — uid is the contract,
    # label is presentation. (TASK-024)
    root_uid = folder_uid(".")
    root_node = GraphNode(
        uid=root_uid,
        kind="folder",
        label="repo-root",
        file_path=None,
        metadata={"extractor": extractor_id, "repo_root": True},
    )
    result.nodes.append(root_node)

    # Emit one folder node per directory segment, and a contains edge
    # from its parent. Parent of first segment is the repo root.
    previous_uid = root_uid
    accumulated: list[str] = []
    for segment in directory_parts:
        accumulated.append(segment)
        this_path = "/".join(accumulated)
        this_uid = folder_uid(this_path)
        result.nodes.append(
            GraphNode(
                uid=this_uid,
                kind="folder",
                label=segment,
                file_path=this_path,
                metadata={"extractor": extractor_id},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=previous_uid,
                target_uid=this_uid,
                edge_type="contains",
                extractor=extractor_id,
                confidence=1.0,
            )
        )
        previous_uid = this_uid

    # Finally the deepest folder → file edge.
    result.edges.append(
        GraphEdge(
            source_uid=previous_uid,
            target_uid=file_uid_,
            edge_type="contains",
            extractor=extractor_id,
            confidence=1.0,
        )
    )


def _promote_stubs(result: ExtractionResult) -> None:
    """Emit a minimal stub node for every edge target we do not own."""
    known = {n.uid for n in result.nodes}
    seen_extra: set[str] = set()
    for edge in result.edges:
        for uid in (edge.source_uid, edge.target_uid):
            if uid in known or uid in seen_extra:
                continue
            seen_extra.add(uid)
            result.nodes.append(_stub_for_uid(uid))


def _stub_for_uid(uid: str) -> GraphNode:
    if uid.startswith("folder:"):
        path = uid[len("folder:") :]
        label = PurePosixPath(path).name if path not in ("", ".") else "."
        return GraphNode(
            uid=uid,
            kind="folder",
            label=label or path or ".",
            file_path=path if path not in ("", ".") else None,
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    if uid.startswith("doc:file:"):
        rest = uid[len("doc:file:") :]
        path, _, anchor = rest.partition("#")
        label = PurePosixPath(path).name if path else anchor
        return GraphNode(
            uid=uid,
            kind="doc:file",
            label=label or uid,
            file_path=path or None,
            lang="md",
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    if uid.startswith("doc:heading:"):
        return GraphNode(
            uid=uid,
            kind="doc:heading",
            label=uid.split("#", 1)[-1] or uid,
            lang="md",
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    if uid.startswith("doc:external:"):
        return GraphNode(
            uid=uid,
            kind="doc:external",
            label=uid[len("doc:external:") :],
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    # Infer kind from any standard `<kind>:<sub>:...` prefix so cross-
    # extractor edge targets (code symbols, mcp tools, routes, tasks)
    # keep the correct kind when synthesised as stubs. Falls through to
    # doc:external only when the prefix is genuinely unknown.
    head, sep, rest = uid.partition(":")
    if sep and head in {"code", "doc", "cos", "task"}:
        sub, sep2, tail = rest.partition(":")
        if sep2:
            kind = f"{head}:{sub}"
            label = tail.split("::", 1)[-1] or tail or uid
            return GraphNode(
                uid=uid,
                kind=kind,
                label=label,
                metadata={"stub": True, "extractor": EXTRACTOR_ID},
            )
    return GraphNode(
        uid=uid,
        kind="doc:external",
        label=uid,
        metadata={"stub": True, "extractor": EXTRACTOR_ID},
    )


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


__all__ = [
    "EXTRACTOR_ID",
    "ExtractionResult",
    "ParseError",
    "emit_contains_spine",
    "extract",
    "file_uid",
    "folder_uid",
    "frontmatter_key_uid",
    "heading_uid",
    "slugify",
]
