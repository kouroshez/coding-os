"""Ingestion flexibility — local folders, GitHub clones, ZIP archives.

All three paths funnel into `core/graph_os/ingest/base.py::IngestPlan`
so the orchestrator can treat any source uniformly.
"""

from .base import IngestPlan, IngestError, walk_local
from .github import clone_github, GithubSize
from .zip import extract_zip, ZipSize

__all__ = [
    "IngestPlan",
    "IngestError",
    "walk_local",
    "clone_github",
    "GithubSize",
    "extract_zip",
    "ZipSize",
]
