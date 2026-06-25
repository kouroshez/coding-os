"""Decide whether a fresh cos_graph_context consult marker covers an edit target.

Mirrors graph_os.tools.graph: the consult marker is keyed on sha1 of the
repo-relative POSIX path and stores the file's sha256[:16] content_hash at
consult time. The hook hashes disk now and compares — so a consult that went
stale because the file changed is treated as no consult at all.

argv: <marker_dir> <file_path> <repo_root>
stdout: one of "missing" | "fresh" | "stale"
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _rel_path(file_path: str, repo_root: str) -> str | None:
    try:
        target = Path(file_path).resolve()
        root = Path(repo_root).resolve()
        return target.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None


def _disk_hash(file_path: str) -> str | None:
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    if len(sys.argv) < 4:
        print("missing")
        return 0
    marker_dir, file_path, repo_root = sys.argv[1], sys.argv[2], sys.argv[3]

    rel = _rel_path(file_path, repo_root)
    if rel is None:
        print("missing")
        return 0

    key = hashlib.sha1(rel.encode("utf-8")).hexdigest()  # noqa: S324 non-crypto path key
    marker = Path(marker_dir) / f"ctx-{key}"
    if not marker.is_file():
        print("missing")
        return 0

    try:
        recorded = json.loads(marker.read_text(encoding="utf-8")).get("content_hash")
    except (OSError, ValueError):
        print("fresh")  # marker exists but unreadable — consulted, fail open
        return 0

    if not recorded:
        print("fresh")  # consult recorded a file we could not hash — fail open
        return 0

    disk = _disk_hash(file_path)
    print("fresh" if disk == recorded else "stale")
    return 0


if __name__ == "__main__":
    sys.exit(main())
