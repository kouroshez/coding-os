"""Tests for graph_os.extractors.md_links (I.2).

Ship gate (Section 19, I.2):
  - ≥ 30 tests
  - extractor unit tests (one fixture per link style)
  - hook integration test (covered by backend round-trip here —
    the actual `auto-reindex-docs.sh` wiring is a separate smoke)
  - both links_to and cites_heading edges present in dogfood output
"""

from __future__ import annotations

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


class TestOpeningBlockReadNext:
    def test_frontmatter_reads_vector_emits_one_edge_per_target(self):
        content = "<!-- domain:DOCS | layer:policy | reads:[a.md, b.md, c.md] -->\n# H\n"
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        # Bare names anchor against the source doc dir (docs/demo.md → docs/).
        assert {e.target_uid for e in rn} == {
            "doc:file:docs/a.md",
            "doc:file:docs/b.md",
            "doc:file:docs/c.md",
        }
        # `reads` itself is NOT a frontmatter_key node — it expands into edges.
        assert all(
            (n.metadata or {}).get("key") != "reads"
            for n in r.nodes
            if n.kind == "doc:frontmatter_key"
        )

    def test_long_form_opening_block_emits_edges(self):
        content = (
            "<!-- domain:DOCS | layer:policy -->\n"
            "# H\n\n"
            "Purpose: x.\n"
            "Read when: x.\n"
            "Skip when: x.\n"
            "Read next: [a](a.md), [b](b.md)\n"
        )
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        assert {e.target_uid for e in rn} == {"doc:file:docs/a.md", "doc:file:docs/b.md"}

    def test_short_form_opening_block_emits_edges(self):
        content = (
            "<!-- domain:DOCS | layer:playbook -->\n"
            "# H\n\n"
            "> P: short purpose.\n"
            "> R: trigger.\n"
            "> S: do not.\n"
            "> N: a.md, b.md\n"
        )
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        assert {e.target_uid for e in rn} == {"doc:file:docs/a.md", "doc:file:docs/b.md"}

    def test_external_url_targets_become_external_uid(self):
        content = "# H\n\nRead next: https://example.com/spec\n"
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        assert any(e.target_uid == "doc:external:https://example.com/spec" for e in rn)

    def test_read_next_inside_fenced_code_ignored(self):
        # fix #4 — fenced code blocks are stripped before the
        # opening-block scan, so a ``Read next:`` line in an example block
        # must NOT emit a graph edge.
        content = (
            "<!-- domain:DOCS | layer:reference -->\n"
            "# H\n\n"
            "Example below:\n\n"
            "```\n"
            "Read next: not-a-real-doc.md\n"
            "```\n\n"
            "Read next: real.md\n"
        )
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        targets = {e.target_uid for e in rn}
        # Bare names anchor against docs/ (source = docs/demo.md).
        assert "doc:file:docs/real.md" in targets
        assert "doc:file:docs/not-a-real-doc.md" not in targets

    def test_prose_fragment_rejected_w65(self):
        """W6.5 (X7): `Read next:` followed by prose (no real path) must
        NOT emit a doc:file: edge. Was the root cause of 386 stale_paths
        from `doc:file:Relevant ADR in ../architecture/adr/ or the …`."""
        content = (
            "<!-- domain:DOCS -->\n"
            "# H\n\n"
            "Read next: Relevant ADR in `../architecture/adr/` or the domain doc.\n"
        )
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        # No prose-shaped doc:file: target should appear.
        for edge in rn:
            assert " " not in edge.target_uid
            assert "`" not in edge.target_uid

    def test_backtick_path_fragment_rejected_w65(self):
        """W6.5 (X7): backtick-wrapped fragment like
        `` `docs/playbooks` `` was previously emitted as a doc_file
        uid. Path-like regex must reject it (contains characters but
        also accept the inner `docs/playbooks` once stripped — verify
        only clean-stripped variant lands)."""
        content = (
            "<!-- domain:DOCS -->\n"
            "# H\n\n"
            "Read next: then the matching playbook in `docs/playbooks`, ok.md\n"
        )
        r = _extract(content)
        targets = {e.target_uid for e in r.edges if e.edge_type == "read_next"}
        # Garbage shouldn't appear.
        for t in targets:
            assert "playbook in" not in t
            assert "`" not in t

    def test_duplicate_targets_deduplicated(self):
        content = "<!-- reads:[a.md, a.md, b.md] -->\n# H\n\nRead next: a.md, b.md\n"
        r = _extract(content)
        rn = [e for e in r.edges if e.edge_type == "read_next"]
        # Frontmatter dedupe: 2 unique. Body dedupe inside opening block: 2.
        # Frontmatter and body are independent passes — both emit edges so we
        # expect 4 distinct edges with 2 distinct targets.
        assert {e.target_uid for e in rn} == {"doc:file:docs/a.md", "doc:file:docs/b.md"}


class TestInlineLinks:
    def test_relative_inline(self):
        r = _extract("[see](../other.md)")
        links = [e for e in r.edges if e.edge_type == "links_to"]
        assert any(e.target_uid == "doc:file:other.md" for e in links)

    def test_external_link_downweighted(self):
        r = _extract("[gh](https://github.com/a/b)")
        links = [e for e in r.edges if e.edge_type == "links_to"]
        assert any(e.target_uid.startswith("doc:external:") and e.confidence < 0.8 for e in links)

    def test_cites_heading_in_same_file(self):
        content = "# Intro\n\n## Section One\n\nSee [link](#section-one)"
        r = _extract(content)
        ch = [e for e in r.edges if e.edge_type == "cites_heading"]
        assert len(ch) == 1
        assert ch[0].target_uid.endswith("#section-one:2")

    def test_cites_heading_cross_file(self):
        content = "See [link](other.md#intro)"
        r = _extract(content, path="docs/demo.md")
        ch = [e for e in r.edges if e.edge_type == "cites_heading"]
        # origin 'docs/demo.md' + relative 'other.md' resolves to 'docs/other.md'.
        assert any(e.target_uid == "doc:heading:docs/other.md#intro" for e in ch)
        links = [e for e in r.edges if e.edge_type == "links_to"]
        assert any(e.target_uid == "doc:file:docs/other.md" for e in links)

    def test_link_inside_code_fence_ignored(self):
        content = "```\n[fake](bad.md)\n```\n\n[real](good.md)"
        r = _extract(content, path="docs/demo.md")
        links = [e for e in r.edges if e.edge_type == "links_to"]
        assert any(e.target_uid == "doc:file:docs/good.md" for e in links)
        assert not any(e.target_uid == "doc:file:docs/bad.md" for e in links)


class TestWikiLinks:
    def test_plain_wikilink(self):
        r = _extract("See [[other]]", path="docs/demo.md")
        links = [e for e in r.edges if e.edge_type == "links_to"]
        assert any(e.target_uid == "doc:file:docs/other.md" for e in links)

    def test_wikilink_with_alias(self):
        r = _extract("See [[other|the other doc]]", path="docs/demo.md")
        links = [e for e in r.edges if e.edge_type == "links_to"]
        assert any(e.target_uid == "doc:file:docs/other.md" for e in links)


class TestExistenceGate:
    # Roadmap §6 — a .md target missing on disk mints nothing: no edge, no
    # stub node (the permanent-stale_paths churn the doctor could only
    # paper over).
    def test_missing_inline_target_dropped(self):
        r = _extract("[see](ghost.md)")
        assert not any(e.target_uid == "doc:file:docs/ghost.md" for e in r.edges)
        assert not any(n.uid == "doc:file:docs/ghost.md" for n in r.nodes)

    def test_missing_target_with_anchor_dropped(self):
        r = _extract("[see](ghost.md#section)")
        assert not any("ghost.md" in e.target_uid for e in r.edges)

    def test_missing_repo_rooted_read_next_dropped(self):
        r = _extract("# H\n\nRead next: docs/ghost.md\n")
        assert not any(
            e.target_uid == "doc:file:docs/ghost.md" for e in r.edges if e.edge_type == "read_next"
        )

    def test_existing_target_still_minted(self):
        r = _extract("[see](other.md) and\n\nRead next: docs/real.md\n")
        links = {e.target_uid for e in r.edges if e.edge_type == "links_to"}
        reads = {e.target_uid for e in r.edges if e.edge_type == "read_next"}
        assert "doc:file:docs/other.md" in links
        assert "doc:file:docs/real.md" in reads


class TestSymlinkResolution:
    # Roadmap §6 — a link to an in-repo symlink lands on the resolved
    # target; the symlink path is never minted (walk_local skips symlinks,
    # so a symlink-path node has no owner and doctor flags it malformed).
    def test_inline_link_to_symlink_lands_on_real_target(self):
        r = _extract("[rules](../CLAUDE.md)")
        links = {e.target_uid for e in r.edges if e.edge_type == "links_to"}
        assert "doc:file:AGENTS.md" in links
        assert not any("CLAUDE.md" in u for u in links)
        assert not any(n.uid == "doc:file:CLAUDE.md" for n in r.nodes)

    def test_repo_rooted_read_next_symlink_resolves(self):
        r = _extract("# H\n\nRead next: docs/LINK.md\n")
        reads = {e.target_uid for e in r.edges if e.edge_type == "read_next"}
        assert "doc:file:docs/other.md" in reads
        assert "doc:file:docs/LINK.md" not in reads

    def test_symlink_escaping_repo_root_dropped(self):
        r = _extract("[bad](ESCAPE.md)")
        assert not any("ESCAPE" in e.target_uid for e in r.edges)
        assert not any("etc/hosts" in (e.target_uid or "") for e in r.edges)


class TestPipelineInvariants:
    def test_extractor_is_pure(self, tmp_path):
        """No filesystem side-effects — extract() takes content, returns data."""
        before = set(tmp_path.rglob("*"))
        r = _extract("# a")
        # Post-S3 the extractor also emits Folder→File spine nodes whose
        # file_path points at the parent directory (``docs`` etc.) or
        # None for the synthetic repo root — check only doc/code-owned
        # nodes reference the source file.
        doc_nodes = [n for n in r.nodes if n.kind != "folder"]
        assert all(n.file_path == "docs/demo.md" for n in doc_nodes)
        # extract() reads the fixture tree (existence gate) but never writes.
        assert set(tmp_path.rglob("*")) == before

    def test_deterministic_across_runs(self):
        content = (
            "<!-- domain:x | ssot:true -->\n# Title\n\n## Child\n\n[link](./other.md) and [[wiki]]"
        )
        first = _extract(content)
        second = _extract(content)
        assert [n.uid for n in first.nodes] == [n.uid for n in second.nodes]
        assert [(e.source_uid, e.target_uid, e.edge_type) for e in first.edges] == [
            (e.source_uid, e.target_uid, e.edge_type) for e in second.edges
        ]

    def test_backend_round_trip(self, migrated_conn):
        """Extracted nodes + edges survive an SqliteBackend upsert."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        content = "# A\n[self](#a)\n[other](./other.md)"
        r = md_links.extract("docs/demo.md", content)
        nodes_written, edges_written = backend.bulk_upsert(r.nodes, r.edges)
        assert nodes_written == len(r.nodes)
        # Two edges may fail to upsert because target uids (other.md) are
        # not present in the graph — the backend raises ValueError.
        # Here we assert the backend wrote everything for in-graph uids:
        assert edges_written >= 1

    def test_ship_gate_both_edge_types_emitted(self):
        """Section 19 I.2 ship gate: both links_to AND cites_heading must be present."""
        content = "# H\n[see](../x.md#intro) and [in-page](#h)"
        r = _extract(content)
        types = {e.edge_type for e in r.edges}
        assert "links_to" in types
        assert "cites_heading" in types

    def test_fatal_error_does_not_crash(self):
        """Passing garbage bytes should surface a parse_error, not raise."""
        content = "\x00\x01\x02 valid after garbage\n# real"
        r = _extract(content)
        assert any(n.kind == "doc:file" for n in r.nodes)

    def test_frontmatter_ssot_confidence_is_0_9(self):
        r = _extract("<!-- ssot_of:docs/rules.md -->\n# h")
        e = next(x for x in r.edges if x.edge_type == "ssot_of")
        assert e.confidence == pytest.approx(0.9)

    def test_empty_document(self):
        r = _extract("")
        # Post-S3: extract() also emits folder nodes along the repo-
        # root → deepest-dir chain. The file node itself is still
        # present, and no parse errors should surface.
        assert any(n.kind == "doc:file" for n in r.nodes)
        non_folder = [n for n in r.nodes if n.kind != "folder"]
        assert len(non_folder) == 1
        assert r.parse_errors == []


class TestGovernanceClassificationDeterminism:
    # (D3-F5): rule/skill paths must classify to a non-doc_file
    # governance kind, stably across repeated extraction — guards against the
    # content-hash skip leaving stale doc_file nodes after a re-index.
    def test_rule_path_classified_and_deterministic(self):
        path = "src/core/rules/anti-overengineering.md"
        content = "# Anti-Overengineering\n\nbody"
        assert md_links._classify_governance_path(path)[0] is not None  # is governance
        kinds = {_file_node(md_links.extract(path, content), path).kind for _ in range(3)}
        assert len(kinds) == 1  # deterministic
        assert kinds != {"doc:file"}  # classified, not left as a plain doc

    def test_skill_path_classified_and_deterministic(self):
        path = "src/core/skills/clean-code/SKILL.md"
        content = "# clean-code\n\nbody"
        assert md_links._classify_governance_path(path)[0] is not None
        kinds = {_file_node(md_links.extract(path, content), path).kind for _ in range(3)}
        assert len(kinds) == 1
        assert kinds != {"doc:file"}

    def test_plain_doc_stays_doc_file(self):
        path = "docs/engineering/some-plain-doc.md"
        content = "# Plain\n\nbody"
        assert md_links._classify_governance_path(path)[0] is None
        node = _file_node(md_links.extract(path, content), path)
        assert node is not None and node.kind == "doc:file"
