"""Markdown link-target resolution — relative paths, anchors, symlinks, assets.

A link target only becomes an edge when it resolves to something the graph can
own; everything else (external URLs, missing files, binary assets) is either
classified as external or dropped here rather than downstream.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ._extract_base import _normalize_path

_ASSET_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".bmp",
        ".pdf",
        ".mp4",
        ".mov",
        ".webm",
        ".mp3",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".zip",
    }
)


def _resolve_through_symlink(normalised: str) -> str:
    # In-repo symlink target (CLAUDE.md → AGENTS.md): land the edge on the
    # real file — walk_local skips symlinks, so a symlink-path node has no
    # owner and doctor flags it malformed (roadmap §6). A symlink escaping
    # the repo root resolves to "" (caller drops it).
    path = Path(normalised)
    if not normalised or not path.is_symlink():
        return normalised
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (OSError, ValueError):
        return ""


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
    # Repo-root fallback: a doc nested deep in the meta-repo can
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
    normalised = _resolve_through_symlink(normalised)
    if not normalised:
        return ""
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
        # permanent stale/orphan junk invisible to the doctor.
        return ""
    if suffix in {".md", ".mdx"} and not Path(normalised).is_file():
        # Broken doc link (target moved/deleted/consumer-only) — same drop
        # policy as the extensionless placeholders above; minting a stub
        # here is permanent stale_paths churn (existence gate: roadmap §6).
        return ""
    if suffix not in {".md", ".mdx", ""} and not Path(normalised).is_file():
        # Non-doc local target (.yaml/.py/.json/…) that does not exist on
        # disk — a broken/stale link (e.g. a render-dir COPY whose relative
        # path resolves one level short → code:file:core/hooks/registry.yaml).
        # The .md gate above already drops missing doc links; widen the same
        # existence gate to every extension so no broken code:file stub is
        # minted (roadmap §6, TASK-410).
        return ""
    if suffix in {".md", ".mdx", ""}:
        base = f"doc:file:{normalised}"
    elif normalised.startswith("docs/tasks/"):
        base = f"task:file:{normalised}"
    else:
        # Code-file nodes carry no line/heading anchor (the uid scheme has no
        # line numbers): a `foo.py#L954` link resolves to the file node, not a
        # phantom `code:file:...#L954` that pollutes similarity.
        return f"code:file:{normalised}"
    return f"{base}#{anchor}" if anchor else base


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
