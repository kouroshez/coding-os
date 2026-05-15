"""Guard: core/scaffold_manifest.json must match the current templates.

Regenerates the manifest into a temp location and compares against the
committed file. If this test fails, run `make manifest-regen` and commit
the updated manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "src" / "core" / "scaffold_manifest.json"


@pytest.mark.slow
def test_committed_manifest_matches_current_templates() -> None:
    """Regenerate manifest in-memory and diff against committed version."""
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.generate_manifest import build_manifest

    fresh = build_manifest()
    committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    fresh_sections = fresh["sections"]
    committed_sections = committed["sections"]

    assert set(fresh_sections.keys()) == set(committed_sections.keys()), (
        "manifest sections differ — run `make manifest-regen`"
    )

    for section_id in fresh_sections:
        fresh_paths = set(fresh_sections[section_id]["paths"])
        committed_paths = set(committed_sections[section_id]["paths"])
        missing = committed_paths - fresh_paths
        extra = fresh_paths - committed_paths
        assert not missing and not extra, (
            f"manifest section '{section_id}' is stale — "
            f"run `make manifest-regen`.\n"
            f"  missing from fresh: {sorted(missing)[:10]}\n"
            f"  extra in fresh:     {sorted(extra)[:10]}"
        )


def test_manifest_file_exists_and_parses() -> None:
    """Cheap smoke test that always runs (non-slow)."""
    assert MANIFEST_PATH.exists(), "src/core/scaffold_manifest.json missing"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("version") == 1
    assert "sections" in data
    assert len(data["sections"]) >= 1
    for section_id, section in data["sections"].items():
        assert "paths" in section, f"section {section_id} missing paths"
        assert section["count"] == len(section["paths"])
