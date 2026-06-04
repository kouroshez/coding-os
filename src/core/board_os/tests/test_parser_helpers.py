"""Unit tests for board_os.parser pure helpers.

Targets the reachable uncovered branches in the lean task-markdown parser:
frontmatter parse failure, outcome placeholder, read-first link/backtick
extraction, frontmatter validation warnings, str-list normalisation, and
the H1-derived id/title fallbacks in parse_task.
"""

from __future__ import annotations

from board_os import parser
from board_os.parser import (
    KIND_ENUM,
    _extract_outcome,
    _extract_read_first_paths,
    _normalize_str_list,
    _validate_frontmatter,
    extract_frontmatter,
    is_lean_format,
    parse_task,
)


# ---------------------------------------------------------------------------
# extract_frontmatter
# ---------------------------------------------------------------------------


class TestExtractFrontmatter:
    def test_valid(self):
        fm = extract_frontmatter("---\nid: TASK-1\nstatus: todo\n---\nbody\n")
        assert fm == {"id": "TASK-1", "status": "todo"}

    def test_no_frontmatter_returns_none(self):
        assert extract_frontmatter("# just a heading\n") is None

    def test_malformed_yaml_returns_none(self):
        assert extract_frontmatter("---\nid: [unclosed\n  : :\n---\nbody\n") is None

    def test_non_dict_yaml_returns_none(self):
        assert extract_frontmatter("---\n- just\n- a list\n---\nbody\n") is None

    def test_is_lean_format(self):
        assert is_lean_format("---\nid: x\n---\nbody")
        assert not is_lean_format("# legacy task\n")


# ---------------------------------------------------------------------------
# _extract_outcome
# ---------------------------------------------------------------------------


class TestExtractOutcome:
    def test_plain_outcome(self):
        assert _extract_outcome("**Outcome:** Ship the thing.\n\n") == "Ship the thing."

    def test_html_comment_placeholder_is_none(self):
        # First comment is skipped by the regex; the captured remainder still
        # starts with `<!--` → treated as an unfilled placeholder → None.
        assert _extract_outcome("**Outcome:** <!--a--><!--b-->z\n\n") is None

    def test_missing_outcome_is_none(self):
        assert _extract_outcome("## Other\nnope\n") is None


# ---------------------------------------------------------------------------
# _extract_read_first_paths
# ---------------------------------------------------------------------------


class TestReadFirstPaths:
    def test_markdown_link(self):
        body = "## Read First\n- [spec](docs/spec.md)\n"
        assert _extract_read_first_paths(body) == ("docs/spec.md",)

    def test_backtick_path(self):
        body = "## Read First\n- `docs/other.md`\n"
        assert _extract_read_first_paths(body) == ("docs/other.md",)

    def test_non_bullet_lines_skipped(self):
        body = "## Read First\nintro prose\n- `a.md`\n"
        assert _extract_read_first_paths(body) == ("a.md",)

    def test_no_section_empty(self):
        assert _extract_read_first_paths("## Outcome\nx\n") == ()


# ---------------------------------------------------------------------------
# _validate_frontmatter
# ---------------------------------------------------------------------------


class TestValidateFrontmatter:
    def test_clean_frontmatter_no_warnings(self):
        assert (
            _validate_frontmatter({"status": "in_progress", "kind": "feature", "priority": "P2"})
            == []
        )

    def test_bad_status(self):
        w = _validate_frontmatter({"status": "bogus"})
        assert any("status" in x for x in w)

    def test_bad_kind_and_priority(self):
        w = _validate_frontmatter({"kind": "nope", "priority": "P99"})
        assert any("kind" in x for x in w)
        assert any("priority" in x for x in w)

    def test_bad_appetite_shape(self):
        w = _validate_frontmatter({"appetite": "forever"})
        assert any("appetite" in x for x in w)

    def test_label_colliding_with_kind_enum(self):
        kind_val = next(iter(KIND_ENUM))
        w = _validate_frontmatter({"labels": [kind_val]})
        assert any("collides" in x for x in w)


# ---------------------------------------------------------------------------
# _normalize_str_list
# ---------------------------------------------------------------------------


class TestNormalizeStrList:
    def test_none(self):
        assert _normalize_str_list(None) == ()

    def test_str_becomes_single(self):
        assert _normalize_str_list("solo") == ("solo",)

    def test_list_filters_falsy(self):
        assert _normalize_str_list(["a", "", "b", None]) == ("a", "b")

    def test_other_type_empty(self):
        assert _normalize_str_list(42) == ()


# ---------------------------------------------------------------------------
# parse_task — lean format + H1 fallbacks
# ---------------------------------------------------------------------------


class TestParseTask:
    def test_full_lean_task(self):
        content = (
            "---\n"
            "id: TASK-001\n"
            "title: Build it\n"
            "status: todo\n"
            "labels: [frontend, urgent]\n"
            "---\n"
            "# TASK-001: Build it\n"
            "**Outcome:** The deliverable.\n\n"
            "## Read First\n- [spec](docs/spec.md)\n"
        )
        t = parse_task(content)
        assert t is not None
        assert t.task_id == "TASK-001"
        assert t.title == "Build it"
        assert t.outcome == "The deliverable."
        assert t.read_first == ("docs/spec.md",)
        assert t.labels == ("frontend", "urgent")
        assert t.is_lean is True

    def test_id_falls_back_to_h1(self):
        content = "---\ntitle: X\n---\n# TASK-042: X\nbody\n"
        t = parse_task(content)
        assert t is not None and t.task_id == "TASK-042"

    def test_title_falls_back_to_h1(self):
        content = "---\nid: TASK-009\n---\n# TASK-009: Derived Title\nbody\n"
        t = parse_task(content)
        assert t is not None and t.title == "Derived Title"

    def test_no_id_anywhere_returns_none(self):
        content = "---\ntitle: orphan\n---\nno heading with an id\n"
        assert parse_task(content) is None
