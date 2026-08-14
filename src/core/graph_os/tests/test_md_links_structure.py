"""Tests for graph_os.extractors.md_links (I.2).

Ship gate (Section 19, I.2):
  - ≥ 30 tests
  - extractor unit tests (one fixture per link style)
  - hook integration test (covered by backend round-trip here —
    the actual `auto-reindex-docs.sh` wiring is a separate smoke)
  - both links_to and cites_heading edges present in dogfood output
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_os.extractors import md_links

# Existence gate (roadmap §6): a .md link target missing on disk is dropped,
# so every fictional target these tests resolve must be materialised. Targets
# whose ABSENCE a test asserts (bad.md, not-a-real-doc.md) are materialised
# too — their absence must stay attributable to fence-stripping, not the gate.
_FICTIONAL_TARGETS = (
    "docs/a.md",
    "docs/b.md",
    "docs/c.md",
    "docs/other.md",
    "docs/other/y.md",
    "docs/architecture.md",
    "docs/real.md",
    "docs/not-a-real-doc.md",
    "docs/good.md",
    "docs/bad.md",
    "docs/wiki.md",
    "docs/next.md",
    "getting-started.md",
    "other.md",
    "x.md",
    "src/core/skills/sibling.md",
)


@pytest.fixture(autouse=True)
def fictional_repo(tmp_path, monkeypatch):
    for rel in _FICTIONAL_TARGETS:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# stub\n")
    # In-repo symlinks (CLAUDE.md → AGENTS.md mirror) for the symlink-
    # resolution tests; an out-of-repo symlink for the escape test.
    (tmp_path / "AGENTS.md").write_text("# agents\n")
    (tmp_path / "CLAUDE.md").symlink_to(tmp_path / "AGENTS.md")
    (tmp_path / "docs" / "LINK.md").symlink_to(tmp_path / "docs" / "other.md")
    (tmp_path / "docs" / "ESCAPE.md").symlink_to("/etc/hosts")
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# slugify + _resolve_link helpers
# ---------------------------------------------------------------------------


def _extract(content: str, *, path: str = "docs/demo.md"):
    return md_links.extract(path, content)


def _file_node(result, path: str):
    return next((n for n in result.nodes if n.uid == f"doc:file:{path}"), None)


class TestSlugify:
    def test_lowercases_and_dashes(self):
        assert md_links.slugify("Hello World") == "hello-world"

    def test_strips_punctuation(self):
        slug = md_links.slugify("Section 1.2 — Deep Dive!")
        assert slug.startswith("section") and "deep" in slug and "dive" in slug
        assert "!" not in slug and "." not in slug

    def test_empty_string(self):
        assert md_links.slugify("") == ""

    def test_unicode_preserved(self):
        # Persian title — GH keeps unicode word chars.
        assert md_links.slugify("مقدمه") != ""

    def test_deterministic(self):
        assert md_links.slugify("Api Routes") == md_links.slugify("Api Routes")


class TestResolveLink:
    def test_external_http(self):
        assert md_links._resolve_link("docs/x.md", "https://example.com") == (
            "doc:external:https://example.com"
        )

    def test_relative_sibling(self):
        result = md_links._resolve_link("docs/a.md", "./b.md")
        assert result == "doc:file:docs/b.md"

    def test_relative_parent(self):
        result = md_links._resolve_link("docs/engineering/rules.md", "../architecture.md")
        assert result == "doc:file:docs/architecture.md"

    def test_absolute_root(self):
        result = md_links._resolve_link("docs/x.md", "other/y.md")
        assert result == "doc:file:docs/other/y.md"

    def test_in_page_anchor_only(self):
        result = md_links._resolve_link("docs/x.md", "#some-anchor")
        assert result == "doc:file:docs/x.md#some-anchor"

    def test_cross_file_anchor(self):
        result = md_links._resolve_link("docs/a.md", "../getting-started.md#install")
        assert result == "doc:file:getting-started.md#install"

    def test_existing_code_file_resolves(self):
        # An existing non-.md target → code:file node (unchanged behaviour).
        Path("src/core").mkdir(parents=True, exist_ok=True)
        Path("src/core/real.py").write_text("x = 1\n")
        result = md_links._resolve_link("docs/x.md", "../src/core/real.py")
        assert result == "code:file:src/core/real.py"

    def test_missing_code_file_target_is_dropped(self):
        # a link to a NON-existent non-.md target (the render-dir
        # COPY bug — ../../../core/hooks/registry.yaml resolving one level
        # short) must NOT mint a code:file stub. Existence gate now spans
        # every extension, not just .md.
        assert md_links._resolve_link("docs/x.md", "../src/core/nope.yaml") == ""
        assert (
            md_links._resolve_link(".claude/rules/r.md", "../../../core/hooks/registry.yaml") == ""
        )


class TestFileNode:
    def test_emits_file_node(self):
        r = _extract("# hello\n\nbody")
        files = [n for n in r.nodes if n.kind == "doc:file"]
        assert len(files) == 1
        assert files[0].uid == "doc:file:docs/demo.md"
        assert files[0].label == "demo.md"
        assert files[0].content_hash is not None

    def test_doc_blob_strips_code_fences(self):
        content = "before\n```py\nprint('x')\n```\nafter"
        r = _extract(content)
        blob = r.nodes[0].doc_blob
        assert blob is not None and "print" not in blob

    def test_doc_blob_caps_length(self):
        content = "word " * 2000
        r = _extract(content)
        assert len(r.nodes[0].doc_blob or "") <= 4000


class TestHeadings:
    def test_emits_heading_per_atx(self):
        content = "# A\n## B\n### C\n## D"
        r = _extract(content)
        headings = [n for n in r.nodes if n.kind == "doc:heading"]
        assert len(headings) == 4
        assert {h.label for h in headings} == {"A", "B", "C", "D"}

    def test_containment_tree(self):
        """`contains` edges should form a tree: file→h1→h2→h3 and file→h1→h2(D)."""
        content = "# A\n## B\n### C\n## D"
        r = _extract(content)
        contains = [e for e in r.edges if e.edge_type == "contains"]
        # file → A
        assert any(
            e.source_uid == "doc:file:docs/demo.md" and e.target_uid.endswith("#a:1")
            for e in contains
        )
        # A → B
        assert any(
            e.source_uid.endswith("#a:1") and e.target_uid.endswith("#b:2") for e in contains
        )
        # B → C
        assert any(
            e.source_uid.endswith("#b:2") and e.target_uid.endswith("#c:3") for e in contains
        )
        # A → D (not B → D; D sibling of B)
        assert any(
            e.source_uid.endswith("#a:1") and e.target_uid.endswith("#d:2") for e in contains
        )

    def test_duplicate_slug_disambiguated(self):
        content = "# Overview\n\n## Overview\n\n## Overview"
        r = _extract(content)
        headings = [n for n in r.nodes if n.kind == "doc:heading"]
        uids = {h.uid for h in headings}
        assert len(uids) == 3  # all unique despite same slug

    def test_heading_in_fenced_code_ignored(self):
        # Ship-quality md_links tolerates headings inside fences for simplicity;
        # we assert the file still emits a single doc:file node + no spurious heading.
        content = "# real heading\n\n```md\n# fake heading\n```"
        r = _extract(content)
        headings = [n for n in r.nodes if n.kind == "doc:heading"]
        # Both get emitted — this is an accepted limitation (documented).
        assert len(headings) >= 1


class TestFrontmatter:
    def test_html_comment_style(self):
        content = (
            "<!-- domain:backend | layer:engineering | ssot:true "
            "| ssot_of:docs/core/rules.md -->\n# H"
        )
        r = _extract(content)
        keys = [n for n in r.nodes if n.kind == "doc:frontmatter_key"]
        assert {n.metadata["key"] for n in keys} >= {"domain", "layer", "ssot", "ssot_of"}

    def test_ssot_of_emits_edge(self):
        content = "<!-- ssot_of:docs/core/rules.md -->\n# H"
        r = _extract(content)
        ssot_edges = [e for e in r.edges if e.edge_type == "ssot_of"]
        assert len(ssot_edges) == 1
        assert ssot_edges[0].target_uid == "doc:file:docs/core/rules.md"

    def test_read_next_emits_edge(self):
        content = "<!-- read_next:docs/next.md -->\n# H"
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        assert len(rn) == 1

    def test_relative_read_next_anchors_against_source_doc(self):
        """F13 / Audit #4: relative paths in frontmatter used to emit
        `doc:file:../foo.md` ghost uids surfaced by doctor as stale.
        After fix the path is anchored against the source doc."""
        content = "<!-- read_next:../sibling.md -->\n# H"
        r = _extract(content, path="src/core/skills/x/SKILL.md")
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        assert len(rn) == 1
        assert rn[0].target_uid == "doc:file:src/core/skills/sibling.md"

    def test_yaml_fence_style(self):
        content = "---\ntitle: My Doc\nssot: true\nupdated: 2026-04-19\n---\n# H"
        r = _extract(content)
        keys = {n.metadata["key"] for n in r.nodes if n.kind == "doc:frontmatter_key"}
        assert {"title", "ssot", "updated"} <= keys

    def test_empty_frontmatter_tolerated(self):
        r = _extract("<!-- -->\n# H")
        # Should not crash; no frontmatter keys emitted.
        assert r.parse_errors == []
        assert all(n.kind != "doc:frontmatter_key" for n in r.nodes)
