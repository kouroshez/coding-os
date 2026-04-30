"""Tests for section index sidecar + cos_doc_section (TASK-165).

PURPOSE:      Lock the contract for the intra-file navigation pipeline:
              `scripts/regen_section_index.py` builds the sidecar,
              `tools.docs.doc_section` reads it. Spec:
              docs/engineering/section-index.md.
INPUT:        synthetic .md files in tmp_path.
OUTPUT:       pytest assertions; no DB / no embeddings / no MCP server.
DEPENDENCIES: stdlib + tools.docs.doc_section + the regen script (loaded
              via importlib so the script's CLI is also exercised).
NOTES:        Must stay quick (<2 s) — runs on every thinking_os matrix.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tools.docs import doc_section


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REGEN_SCRIPT = _REPO_ROOT / "scripts" / "regen_section_index.py"


def _load_regen_module():
    """Import scripts/regen_section_index.py without polluting sys.modules."""
    spec = importlib.util.spec_from_file_location(
        "regen_section_index", _REGEN_SCRIPT,
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["regen_section_index"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def regen():
    return _load_regen_module()


def _fat_doc(tmp_path: Path, *, with_frontmatter: bool = True, sections: int = 6) -> Path:
    """Build a synthetic doc with N H2 sections, each padded past 80 lines.

    A 6-section doc lands well above the 400-line LINE_THRESHOLD.
    """
    parts: list[str] = []
    if with_frontmatter:
        parts.append("<!-- domain:CORE | layer:spec | ssot:true | updated:2026-04-30 -->")
    parts.append("# Synthetic Fat Doc")
    parts.append("")
    parts.append("Intro line for the synthetic fixture.")
    parts.append("")
    for i in range(1, sections + 1):
        parts.append(f"## Section {i} Title")
        parts.append("")
        parts.append(f"Body for section {i}. Keyword{i} repeats here.")
        # Pad with 80 prose lines so each section is fat enough.
        for j in range(80):
            parts.append(
                f"Line {j} of section {i} — keyword{i} payload, prose etc."
            )
        parts.append("")
    target = tmp_path / "fat.md"
    target.write_text("\n".join(parts), encoding="utf-8")
    return target


def test_threshold_skips_small_doc(tmp_path: Path, regen) -> None:
    small = tmp_path / "small.md"
    small.write_text("# Small\n\n## A\nbody\n\n## B\nbody\n", encoding="utf-8")
    body = regen.regenerate(small, write=False)
    assert body is None, "Sub-threshold doc must not get an INDEX"
    assert not (tmp_path / "small.INDEX.md").exists()


def test_force_writes_sidecar(tmp_path: Path, regen) -> None:
    small = tmp_path / "small.md"
    small.write_text("# Small\n\n## A\nbody\n\n## B\nbody\n", encoding="utf-8")
    body = regen.regenerate(small, write=True, force=True)
    assert body is not None
    sidecar = tmp_path / "small.INDEX.md"
    assert sidecar.exists()
    text = sidecar.read_text(encoding="utf-8")
    assert "<!-- BEGIN auto-section-index -->" in text
    assert "<!-- END auto-section-index -->" in text
    assert "small.md" in text


def test_fat_doc_writes_sidecar(tmp_path: Path, regen) -> None:
    src = _fat_doc(tmp_path)
    body = regen.regenerate(src, write=True)
    assert body is not None
    sidecar = src.with_name(src.stem + ".INDEX.md")
    assert sidecar.exists()
    text = sidecar.read_text(encoding="utf-8")
    # Expect one row per H1 + 6 H2 sections.
    assert text.count("| H1 |") >= 1
    assert text.count("| H2 |") == 6


def test_slug_stability_across_edits(tmp_path: Path, regen) -> None:
    src = _fat_doc(tmp_path)
    regen.regenerate(src, write=True)
    sidecar = src.with_name(src.stem + ".INDEX.md")
    first = sidecar.read_text(encoding="utf-8")

    # Edit body content WITHOUT renaming any heading — slugs must be stable.
    src.write_text(src.read_text(encoding="utf-8") + "\nfresh tail line\n", encoding="utf-8")
    regen.regenerate(src, write=True)
    second = sidecar.read_text(encoding="utf-8")

    # All slugs that appeared first time must still be there.
    import re
    slug_re = re.compile(r"`([a-z][a-z0-9-]*)`")
    first_slugs = set(slug_re.findall(first))
    second_slugs = set(slug_re.findall(second))
    assert first_slugs.issubset(second_slugs), (
        "slug must be stable when only body text changes; "
        f"missing: {first_slugs - second_slugs}"
    )


def test_doc_section_returns_body(tmp_path: Path, regen) -> None:
    src = _fat_doc(tmp_path)
    regen.regenerate(src, write=True)
    payload = doc_section(src, slug="section-3-title")
    assert payload is not None
    assert payload["slug"] == "section-3-title"
    assert payload["title"] == "Section 3 Title"
    assert payload["body"].startswith("## Section 3 Title")
    assert "keyword3" in payload["body"]


def test_doc_section_with_body_false_omits_body(tmp_path: Path, regen) -> None:
    src = _fat_doc(tmp_path)
    regen.regenerate(src, write=True)
    payload = doc_section(src, slug="section-2-title", with_body=False)
    assert payload is not None
    assert "body" not in payload
    assert payload["lines"] >= 1


def test_doc_section_fuzzy_title(tmp_path: Path, regen) -> None:
    src = _fat_doc(tmp_path)
    regen.regenerate(src, write=True)
    payload = doc_section(src, section="SECTION 4")
    assert payload is not None
    assert payload["slug"] == "section-4-title"


def test_doc_section_unknown_slug(tmp_path: Path, regen) -> None:
    src = _fat_doc(tmp_path)
    regen.regenerate(src, write=True)
    payload = doc_section(src, slug="does-not-exist")
    assert payload is None


def test_doc_section_no_index(tmp_path: Path) -> None:
    """No sidecar → returns None so caller can degrade gracefully."""
    src = tmp_path / "naked.md"
    src.write_text("# X\n\n## A\nbody\n", encoding="utf-8")
    payload = doc_section(src, slug="a")
    assert payload is None


def test_no_index_for_index_files(tmp_path: Path, regen) -> None:
    """*.INDEX.md and 00-index.md must never be re-indexed."""
    a = tmp_path / "x.INDEX.md"
    a.write_text("# Index\n\n## Foo\nbody\n", encoding="utf-8")
    b = tmp_path / "00-index.md"
    b.write_text("# Index\n\n## Foo\nbody\n", encoding="utf-8")
    assert regen.regenerate(a, write=True, force=True) is None
    assert regen.regenerate(b, write=True, force=True) is None


def test_splice_preserves_prose(tmp_path: Path, regen) -> None:
    """Hand-authored prose outside the auto-section fence must survive regen."""
    src = _fat_doc(tmp_path)
    regen.regenerate(src, write=True)
    sidecar = src.with_name(src.stem + ".INDEX.md")
    # Append a hand-authored note AFTER the END marker.
    text = sidecar.read_text(encoding="utf-8")
    text += "\n## Hand-Authored Notes\n\nDo not clobber me on regen.\n"
    sidecar.write_text(text, encoding="utf-8")

    regen.regenerate(src, write=True)
    refreshed = sidecar.read_text(encoding="utf-8")
    assert "Do not clobber me on regen." in refreshed


def test_giant_section_warning(tmp_path: Path, regen) -> None:
    """A section ≥ GIANT_SECTION_LINES must be flagged in the index."""
    parts = [
        "<!-- domain:CORE | layer:spec | ssot:true | updated:2026-04-30 -->",
        "# Doc",
        "",
        "## Tiny",
        "small",
        "",
        "## Huge",
    ]
    parts.extend(f"line {i}" for i in range(600))
    src = tmp_path / "giant.md"
    src.write_text("\n".join(parts), encoding="utf-8")
    body = regen.regenerate(src, write=True)
    assert body is not None
    sidecar = src.with_name(src.stem + ".INDEX.md")
    text = sidecar.read_text(encoding="utf-8")
    assert "Giant sections" in text
    assert "huge" in text
