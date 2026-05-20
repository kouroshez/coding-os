"""Ingestion flexibility — local folders, GitHub clones, ZIP archives.

All three paths funnel into `core/graph_os/ingest/base.py::IngestPlan`
so the orchestrator can treat any source uniformly.
"""

from .base import IngestError, IngestPlan, walk_local
from .github import GithubSize, clone_github
from .zip import ZipSize, extract_zip

__all__ = [
    "GithubSize",
    "IngestError",
    "IngestPlan",
    "ZipSize",
    "clone_github",
    "extract_zip",
    "walk_local",
]
