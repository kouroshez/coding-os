"""Forge detection and external-ref parsing.

external_ref is an optional bidirectional link to a forge issue/PR — metadata
only, never the task's canonical id (ADR adr-task-id-allocator-seam). Host is
detected from the origin remote, so the kernel hardcodes no forge (P2). A leaf:
the one sibling it reaches is the mcp_tools module object, imported inside the
function so a test patching `mcp_tools._detect_forge` is still what runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("coding_os.board_os.mcp_tools")


def _detect_forge(project_root: Path) -> str:
    import subprocess

    try:
        url = (
            subprocess.run(
                ["git", "-C", str(project_root), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            .stdout.strip()
            .lower()
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    host = _remote_host(url)
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    # Self-hosted GitLab/Bitbucket carry arbitrary hostnames, so the substring
    # heuristic stays — but scoped to the host, never the whole URL.
    if "gitlab" in host:
        return "gitlab"
    if "bitbucket" in host:
        return "bitbucket"
    return ""


def _remote_host(url: str) -> str:
    # Both remote spellings reduce to their host segment: matching the full URL
    # lets a path like https://evil.example/github.com/x impersonate a forge.
    authority = url.split("://", 1)[-1].split("/", 1)[0]
    if "@" in authority:
        authority = authority.split("@", 1)[1]
    return authority.split(":", 1)[0]


def _normalize_external_ref(raw: str, project_root: Path) -> str | None:
    # Accepts a bare number, '#42', 'github#42', or a full issue/PR URL → returns
    # '<forge>#<n>' ('!' for a merge/pull request). Forge is taken from the ref
    # when explicit, else detected from origin; None when unparseable.
    import re as _re

    raw = (raw or "").strip()
    if not raw:
        return None
    m = _re.search(
        r"(github|gitlab|bitbucket)\.[^/]+/.+?/(?:issues|pull|-/issues|-/merge_requests|merge_requests)/(\d+)",
        raw,
    )
    if m:
        sep = "!" if "merge_request" in raw or "/pull/" in raw else "#"
        return f"{m.group(1)}{sep}{m.group(2)}"
    m = _re.match(r"^(github|gitlab|bitbucket)\s*([#!])\s*(\d+)$", raw, _re.IGNORECASE)
    if m:
        return f"{m.group(1).lower()}{m.group(2)}{m.group(3)}"
    m = _re.match(r"^([#!]?)(\d+)$", raw)
    if m:
        from . import mcp_tools as _kernel

        forge = _kernel._detect_forge(project_root)
        if not forge:
            return None
        sep = "!" if m.group(1) == "!" else "#"
        return f"{forge}{sep}{m.group(2)}"
    return None
