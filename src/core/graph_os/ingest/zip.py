"""ZIP ingestion with bomb protection (I.11)."""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .base import IngestError, IngestPlan, walk_local

logger = logging.getLogger("graph_os.ingest.zip")


@dataclass(frozen=True)
class ZipSize:
    max_size_bytes: int = 500 * 1024 * 1024
    max_files: int = 50_000
    max_compression_ratio: int = 20  # decompressed/compressed


def extract_zip(
    archive: str | Path,
    *,
    alias: str | None = None,
    out_dir: Path,
    size: ZipSize = ZipSize(),
) -> IngestPlan:
    """Unzip safely, refuse bombs, then walk.

    RAISES:       IngestError on zip-bomb heuristics or traversal
                  attempts (`../` in any member path).
    """
    archive_path = Path(archive).resolve()
    if not archive_path.is_file():
        raise IngestError(f"archive not found: {archive_path}")
    alias = alias or archive_path.stem
    target_root = out_dir.resolve() / alias
    target_root.mkdir(parents=True, exist_ok=True)

    try:
        zf = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise IngestError(f"bad zip: {exc}") from exc

    compressed_total = 0
    uncompressed_total = 0
    count = 0
    try:
        for member in zf.infolist():
            count += 1
            if count > size.max_files:
                raise IngestError(f"zip has > {size.max_files} entries")
            if member.file_size < 0 or member.compress_size < 0:
                raise IngestError(f"malformed zip entry {member.filename!r}")
            compressed_total += member.compress_size
            uncompressed_total += member.file_size
            if uncompressed_total > size.max_size_bytes:
                raise IngestError(
                    f"uncompressed size exceeds {size.max_size_bytes} bytes"
                )
            if (
                member.compress_size
                and (member.file_size / max(member.compress_size, 1))
                > size.max_compression_ratio
            ):
                raise IngestError(
                    f"suspicious compression ratio on {member.filename!r}"
                )
            # Reject path traversal.
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise IngestError(
                    f"zip traversal blocked: {member.filename!r}"
                )
        zf.extractall(target_root)
    finally:
        zf.close()

    plan = walk_local(
        target_root,
        alias=alias,
        max_files=size.max_files,
        max_size_bytes=size.max_size_bytes,
    )
    plan_source_meta = dict(plan.metadata)
    plan_source_meta.update(
        {
            "zip_compressed_bytes": compressed_total,
            "zip_uncompressed_bytes": uncompressed_total,
        }
    )
    return IngestPlan(
        alias=plan.alias,
        root=plan.root,
        files=plan.files,
        source="zip",
        metadata=plan_source_meta,
    )


__all__ = ["extract_zip", "ZipSize"]
