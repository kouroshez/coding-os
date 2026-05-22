"""Tests for src/scripts/dev/audit_doc_links.py.

The doc-link auditor is a CI hard gate (a broken link or symlinked
docs/ subdir fails the build). Its slug logic already regressed once
— the original implementation collapsed consecutive hyphens, which
GitHub does not. These tests pin the GitHub-fidelity behavior so the
gate cannot silently drift again.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_AUDITOR = _REPO / "src" / "scripts" / "dev" / "audit_doc_links.py"


def _load_auditor():
    spec = importlib.util.spec_from_file_location("audit_doc_links", _AUDITOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_doc_links"] = mod
    spec.loader.exec_module(mod)
    return mod


audit = _load_auditor()


# ---------------------------------------------------------------------------
# _slugify — must match GitHub's github-slugger, NOT collapse hyphens
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_keeps_double_hyphen_from_em_dash(self):
        # `## Rule 0 — Docs-first` → GitHub: rule-0--docs-first (em-dash
        # dropped, the two spaces around it become two hyphens).
        assert audit._slugify("Rule 0 — Docs-first") == "rule-0--docs-first"

    def test_does_not_collapse_consecutive_hyphens(self):
        assert audit._slugify("A — B — C") == "a--b--c"

    def test_lowercases(self):
        assert audit._slugify("UPPER Case") == "upper-case"

    def test_drops_punctuation_keeps_word_chars(self):
        # backticks, slashes, asterisks, dots dropped; words survive.
        assert audit._slugify("hardcoded in `src/cli/*.py`") == "hardcoded-in-srcclipy"

    def test_empty_falls_back_to_section(self):
        assert audit._slugify("!!!") == "section"


# ---------------------------------------------------------------------------
# _strip_for_links — fences, inline code, HTML comments blanked
# ---------------------------------------------------------------------------


class TestStripForLinks:
    def test_blanks_inline_code(self):
        out = audit._strip_for_links("see `[x](y)` here")
        assert "[x](y)" not in out

    def test_blanks_fenced_block(self):
        out = audit._strip_for_links("```\n[x](y)\n```")
        assert "[x](y)" not in out

    def test_blanks_html_comment(self):
        out = audit._strip_for_links("<!-- [x](y) -->")
        assert "[x](y)" not in out

    def test_preserves_real_links(self):
        out = audit._strip_for_links("a real [text](path.md) link")
        assert "[text](path.md)" in out

    def test_preserves_newline_count(self):
        src = "line1\n```\nfenced\n```\nline5"
        assert audit._strip_for_links(src).count("\n") == src.count("\n")


# ---------------------------------------------------------------------------
# _strip_for_headings — KEEPS inline code (heading slugs include it)
# ---------------------------------------------------------------------------


class TestStripForHeadings:
    def test_keeps_inline_code(self):
        # A heading's code-span text is part of the GitHub anchor.
        out = audit._strip_for_headings("## Rule 1 — hardcode `core/`")
        assert "core/" in out

    def test_blanks_fenced_block(self):
        out = audit._strip_for_headings("```\n## Not A Heading\n```")
        assert "## Not A Heading" not in out


# ---------------------------------------------------------------------------
# _is_external
# ---------------------------------------------------------------------------


class TestIsExternal:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com", True),
            ("http://example.com", True),
            ("docs/governance/x.md", False),
            ("../adr/0000-index.md", False),
            ("#anchor", False),
        ],
    )
    def test_classification(self, url, expected):
        assert audit._is_external(url) is expected


# ---------------------------------------------------------------------------
# _gather_anchors — heading → anchor set, dup headings get -N suffix
# ---------------------------------------------------------------------------


class TestGatherAnchors:
    def test_collects_heading_slugs(self):
        anchors = audit._gather_anchors("# Title\n## Section One\n## Section Two\n")
        assert "section-one" in anchors
        assert "section-two" in anchors

    def test_duplicate_heading_gets_numeric_suffix(self):
        anchors = audit._gather_anchors("## Dup\n## Dup\n")
        assert "dup" in anchors
        assert "dup-1" in anchors


# ---------------------------------------------------------------------------
# _check_symlink_dirs — the GitHub-404 guard
# ---------------------------------------------------------------------------


class TestCheckSymlinkDirs:
    def test_real_docs_tree_has_no_symlink_dirs(self):
        # Regression guard: docs/governance + docs/workflow were once
        # symlinks; this must stay empty.
        findings = audit._check_symlink_dirs()
        assert findings == [], f"symlinked docs/ dirs found: {findings}"
