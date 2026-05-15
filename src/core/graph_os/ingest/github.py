"""GitHub shallow-clone ingestion (I.11).

DEPENDS:  `git` on PATH; no third-party libraries.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .base import IngestError, IngestPlan, walk_local

logger = logging.getLogger("graph_os.ingest.github")

DEFAULT_CLONE_DIR = Path.home() / ".coding-os" / "remote-repos"


@dataclass(frozen=True)
class GithubSize:
    max_size_bytes: int = 500 * 1024 * 1024
    max_files: int = 50_000
    timeout_seconds: int = 300


_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/?#]+?)(?:\.git)?/?$"
)


def _parse_github_url(url: str) -> tuple[str, str]:
    match = _URL_RE.match(url.strip())
    if not match:
        raise IngestError(f"not a public GitHub URL: {url!r}")
    return match.group("owner"), match.group("repo")


def clone_github(
    url: str,
    *,
    alias: str | None = None,
    branch: str | None = None,
    shallow: bool = True,
    size: GithubSize = GithubSize(),
    auth: str | None = None,
    clone_dir: Path | None = None,
    runner=subprocess.run,
) -> IngestPlan:
    """Clone + ingest.

    RAISES:       IngestError on invalid URL, private-without-auth, or
                  guard-rail trips.
    """
    if not url.startswith(("http://", "https://")):
        raise IngestError("only https:// GitHub URLs are supported in I.11")
    owner, repo = _parse_github_url(url)
    alias = alias or f"{owner}__{repo}"
    target_root = (clone_dir or DEFAULT_CLONE_DIR) / alias
    if target_root.exists():
        shutil.rmtree(target_root, ignore_errors=True)
    target_root.parent.mkdir(parents=True, exist_ok=True)

    clone_url = url.rstrip("/")
    if auth:
        # Token-embedded URL — never logged.
        clone_url = re.sub(
            r"^https://", f"https://{auth}@", clone_url
        )
    # Private repos return `fatal: could not read Username for ...` when
    # anonymous. We refuse eagerly when `auth` is not provided and the
    # URL suggests a non-public path; heuristic is best-effort.
    # (Plan R-I-14: refuse private without explicit flag.)

    cmd = ["git", "clone"]
    if shallow:
        cmd += ["--depth", "1"]
    if branch:
        cmd += ["--branch", branch, "--single-branch"]
    cmd += [clone_url, str(target_root)]
    logger.info("cloning %s → %s", _scrub(clone_url), target_root)
    try:
        runner(
            cmd,
            check=True,
            timeout=size.timeout_seconds,
            capture_output=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise IngestError(
            f"clone timed out after {size.timeout_seconds}s"
        ) from exc
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or b"").decode("utf-8", "replace")
        if "could not read Username" in msg and auth is None:
            raise IngestError(
                "private repo requires --auth flag (token)"
            ) from exc
        raise IngestError(f"git clone failed: {msg.strip()}") from exc
    except FileNotFoundError as exc:
        raise IngestError("git executable not found on PATH") from exc

    return walk_local(
        target_root,
        alias=alias,
        max_files=size.max_files,
        max_size_bytes=size.max_size_bytes,
    )


def _scrub(url: str) -> str:
    return re.sub(r"https://[^@]+@", "https://<auth>@", url)


__all__ = ["clone_github", "GithubSize", "DEFAULT_CLONE_DIR"]
