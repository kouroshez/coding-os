"""
Tests for core/thinking_os/task_parser.py — Phase C.2 pure parser.

All tests run without `rag` extras — the parser has zero ML dependencies.
Coverage:
  - extract_task_id_from_h1 edge cases
  - front-matter stripping
  - Goal first-paragraph extraction
  - Scope In/Out subsection parsing
  - Requirements numbered-list parsing
  - Dependencies extraction (dedupe, order, partial-match safety)
  - content_hash determinism
  - End-to-end parse of the real NakoDigital TASK-199 fixture
  - Edge cases: missing sections, minimal task, non-task markdown
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from task_parser import (
    ParsedTask,
    _compute_content_hash,
    _strip_front_matter,
    extract_dependencies,
    extract_task_id_from_h1,
    parse_task_file,
)


# Real TASK-199 content from NakoDigital, used as an end-to-end fixture.
# Kept as a constant so the test doesn't depend on an external file.
NAKO_TASK_199 = """\
<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-03-29 -->
# TASK-199: [BACKEND] Commission model

Purpose: Implement the platform commission structure for seller transactions.
Read when: Working on this exact task.
Skip when: Another task is active.

> Nav: [Tasks Index](../tasks.md) | [Docs Index](../00-index.md)

- Created: 2026-03-29

## Goal

Design and implement a flexible commission model that calculates the platform's cut from each seller transaction. Support tiered commission rates (by seller tier, product category, or volume), flat fee + percentage combinations, and promotional overrides. Commission is calculated at checkout and recorded per order line item.

## Read First

- `docs/PRD/12a-commerce-schema.md` — commerce schema
- `docs/architecture/08-payment-architecture.md` — payment flow
- `backend/apps/orders/models/` — order models
- `docs/engineering/backend-rules.md` — backend conventions

## Source of Truth

- `backend/apps/marketplace/models/commission.py` (new)
- `backend/apps/marketplace/services/commission_service.py` (new)

## Scope

### In

- CommissionRule model (rate_percent, flat_fee, category, seller_tier, effective_date)
- CommissionRecord model (order_line, seller, gross_amount, commission_amount, net_amount)
- Commission calculation service
- Default commission rate configuration
- Category-specific commission overrides
- Seller-tier commission overrides
- Commission calculation at order creation time
- Admin endpoints to manage commission rules

### Out

- DO NOT implement payout processing (TASK-201)
- DO NOT build earnings tracking aggregation (TASK-200)
- DO NOT implement promotional commission discounts (future enhancement)

## Requirements

1. Given a seller product sale, when the order is created, then commission is calculated using the applicable rule and a CommissionRecord is created
2. Given category-specific and default rules, when calculating commission, then the most specific matching rule is applied
3. Given a commission rule change, when new orders are placed, then the new rate applies (existing records unaffected)
4. Given an order with multiple seller products, when processing, then commission is calculated per line item

## Dependencies

- TASK-195 — seller product CRUD (products must be associated with sellers)

## Open Questions

- None.

## Rabbit Holes

- None.

## Verification

- `make lint-backend && make test-backend` passes
- Commission calculated correctly for various rule combinations
- CommissionRecord created for each seller line item
- Admin can create/update commission rules

## Notes

### Session Checkpoint

- **Progress:** Not started
- **Next Step:** Design CommissionRule model schema and priority resolution logic
"""


# ---------------------------------------------------------------------------
# extract_task_id_from_h1
# ---------------------------------------------------------------------------

class TestExtractH1:
    def test_extracts_task_id_domain_title(self) -> None:
        task_id, domain, title = extract_task_id_from_h1("TASK-199: [BACKEND] Commission model")
        assert task_id == "TASK-199"
        assert domain == "BACKEND"
        assert title == "Commission model"

    def test_title_without_domain_tag(self) -> None:
        task_id, domain, title = extract_task_id_from_h1("TASK-003: Simple task without tag")
        assert task_id == "TASK-003"
        assert domain is None
        assert title == "Simple task without tag"

    def test_zero_pads_task_id(self) -> None:
        """Single-digit task numbers should become TASK-003 not TASK-3."""
        task_id, _, _ = extract_task_id_from_h1("TASK-3: Tiny task")
        assert task_id == "TASK-003"

    def test_malformed_h1_returns_none_id(self) -> None:
        task_id, domain, title = extract_task_id_from_h1("Not a task heading")
        assert task_id is None
        assert domain is None
        assert title == "Not a task heading"

    def test_domain_with_hyphen(self) -> None:
        """Domain tags like [FULL-STACK] should be accepted."""
        task_id, domain, title = extract_task_id_from_h1("TASK-042: [FULL-STACK] API + UI")
        assert task_id == "TASK-042"
        assert domain == "FULL-STACK"

    def test_strips_surrounding_whitespace(self) -> None:
        task_id, _, title = extract_task_id_from_h1("  TASK-001:   Trim me   ")
        assert task_id == "TASK-001"
        assert title == "Trim me"


# ---------------------------------------------------------------------------
# _strip_front_matter
# ---------------------------------------------------------------------------

class TestStripFrontMatter:
    def test_removes_comment_header(self) -> None:
        content = (
            "<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-04-06 -->\n"
            "# TASK-001: Test\n"
        )
        stripped = _strip_front_matter(content)
        assert "domain:BACKEND" not in stripped
        assert "# TASK-001" in stripped

    def test_no_front_matter_unchanged(self) -> None:
        content = "# TASK-001: Plain\n\nNo front-matter here."
        assert _strip_front_matter(content) == content

    def test_only_strips_first_comment(self) -> None:
        """Comments later in the body (e.g. in code fences) must survive."""
        content = (
            "<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-04-06 -->\n"
            "# Task\n\n"
            "<!-- domain:OTHER --> should stay\n"
        )
        stripped = _strip_front_matter(content)
        assert "domain:BACKEND" not in stripped
        assert "domain:OTHER" in stripped


# ---------------------------------------------------------------------------
# extract_dependencies
# ---------------------------------------------------------------------------

class TestExtractDependencies:
    def test_single_dependency(self) -> None:
        text = "- TASK-195 — seller product CRUD"
        assert extract_dependencies(text) == ["TASK-195"]

    def test_multiple_dependencies(self) -> None:
        text = (
            "- TASK-195 — seller product CRUD\n"
            "- TASK-200 — earnings tracking\n"
        )
        assert extract_dependencies(text) == ["TASK-195", "TASK-200"]

    def test_dedupe_preserves_first_appearance_order(self) -> None:
        text = "- TASK-200 first\n- TASK-195 second\n- TASK-200 duplicate\n"
        assert extract_dependencies(text) == ["TASK-200", "TASK-195"]

    def test_none_literal_returns_empty(self) -> None:
        assert extract_dependencies("- None.") == []
        assert extract_dependencies("None.") == []
        assert extract_dependencies("none") == []

    def test_empty_string_returns_empty(self) -> None:
        assert extract_dependencies("") == []
        assert extract_dependencies("   ") == []

    def test_task_ref_in_prose(self) -> None:
        """A TASK-### reference in prose (not a bullet) should still be detected."""
        text = "Depends on TASK-042 for schema design."
        assert extract_dependencies(text) == ["TASK-042"]

    def test_no_partial_match_task19_vs_task195(self) -> None:
        """TASK-19 must NOT be returned when only TASK-195 is present.

        This is a critical correctness check — word boundary matching must
        prevent substring false positives that would corrupt dependents queries.
        """
        text = "- TASK-195 — seller CRUD"
        deps = extract_dependencies(text)
        assert deps == ["TASK-195"]
        assert "TASK-19" not in deps

    def test_zero_pads_numbers(self) -> None:
        """TASK-3 in source → canonical TASK-003 in output."""
        text = "- TASK-3 — some dependency"
        assert extract_dependencies(text) == ["TASK-003"]


# ---------------------------------------------------------------------------
# _compute_content_hash
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_hash_length_16(self) -> None:
        assert len(_compute_content_hash("anything")) == 16

    def test_hash_deterministic(self) -> None:
        assert _compute_content_hash("same") == _compute_content_hash("same")

    def test_hash_differs_for_different_content(self) -> None:
        assert _compute_content_hash("a") != _compute_content_hash("b")


# ---------------------------------------------------------------------------
# parse_task_file — end-to-end on the real TASK-199 fixture
# ---------------------------------------------------------------------------

class TestParseTaskFileRealFixture:
    @pytest.fixture
    def parsed(self) -> ParsedTask:
        result = parse_task_file(NAKO_TASK_199)
        assert result is not None, "TASK-199 fixture should parse successfully"
        return result

    def test_task_id_parsed(self, parsed: ParsedTask) -> None:
        assert parsed.task_id == "TASK-199"

    def test_domain_parsed(self, parsed: ParsedTask) -> None:
        assert parsed.domain == "BACKEND"

    def test_title_stripped_of_prefix(self, parsed: ParsedTask) -> None:
        assert parsed.title == "Commission model"

    def test_raw_title_preserved(self, parsed: ParsedTask) -> None:
        assert parsed.raw_title == "TASK-199: [BACKEND] Commission model"

    def test_goal_is_first_paragraph(self, parsed: ParsedTask) -> None:
        assert parsed.goal_text.startswith("Design and implement a flexible commission model")
        # Should be one paragraph — no double newlines
        assert "\n\n" not in parsed.goal_text

    def test_read_first_extracted(self, parsed: ParsedTask) -> None:
        assert len(parsed.read_first) == 4
        assert any("PRD/12a-commerce-schema.md" in item for item in parsed.read_first)

    def test_source_of_truth_extracted(self, parsed: ParsedTask) -> None:
        assert len(parsed.source_of_truth) == 2
        assert any("commission.py" in item for item in parsed.source_of_truth)

    def test_scope_in_extracted(self, parsed: ParsedTask) -> None:
        assert len(parsed.scope_in) == 8
        assert any("CommissionRule model" in item for item in parsed.scope_in)

    def test_scope_out_extracted(self, parsed: ParsedTask) -> None:
        assert len(parsed.scope_out) == 3
        assert any("payout processing" in item for item in parsed.scope_out)

    def test_requirements_numbered_parsed(self, parsed: ParsedTask) -> None:
        assert len(parsed.requirements) == 4
        assert parsed.requirements[0].startswith("Given a seller product sale")

    def test_dependencies_parsed(self, parsed: ParsedTask) -> None:
        assert parsed.dependencies == ["TASK-195"]

    def test_open_questions_parsed(self, parsed: ParsedTask) -> None:
        assert "None." in parsed.open_questions

    def test_rabbit_holes_parsed(self, parsed: ParsedTask) -> None:
        assert "None." in parsed.rabbit_holes

    def test_verification_parsed(self, parsed: ParsedTask) -> None:
        assert "make lint-backend" in parsed.verification

    def test_content_hash_populated(self, parsed: ParsedTask) -> None:
        assert len(parsed.content_hash) == 16


# ---------------------------------------------------------------------------
# parse_task_file — edge cases
# ---------------------------------------------------------------------------

class TestParseTaskFileEdgeCases:
    def test_empty_content_returns_none(self) -> None:
        assert parse_task_file("") is None
        assert parse_task_file("   ") is None

    def test_no_h1_returns_none(self) -> None:
        assert parse_task_file("Just some text with no heading.") is None

    def test_h1_without_task_prefix_returns_none(self) -> None:
        assert parse_task_file("# Just a regular markdown file\n\nContent.") is None

    def test_minimal_task_only_goal(self) -> None:
        content = (
            "# TASK-042: Minimal\n\n"
            "## Goal\n\n"
            "Do something simple.\n"
        )
        parsed = parse_task_file(content)
        assert parsed is not None
        assert parsed.task_id == "TASK-042"
        assert parsed.goal_text == "Do something simple."
        assert parsed.scope_in == []
        assert parsed.scope_out == []
        assert parsed.requirements == []
        assert parsed.dependencies == []

    def test_missing_goal_returns_empty_goal_text(self) -> None:
        content = (
            "# TASK-007: No goal\n\n"
            "## Verification\n\n"
            "- Make sure it works.\n"
        )
        parsed = parse_task_file(content)
        assert parsed is not None
        assert parsed.goal_text == ""

    def test_scope_without_subsections_returns_empty_lists(self) -> None:
        """A Scope section with no ### In / ### Out should yield empty sublists."""
        content = (
            "# TASK-010: Flat scope\n\n"
            "## Goal\n\nX.\n\n"
            "## Scope\n\n"
            "Just prose here with no subsections.\n"
        )
        parsed = parse_task_file(content)
        assert parsed is not None
        assert parsed.scope_in == []
        assert parsed.scope_out == []

    def test_multiple_dependencies_in_bullets(self) -> None:
        content = (
            "# TASK-100: Multi-dep\n\n"
            "## Goal\n\nX.\n\n"
            "## Dependencies\n\n"
            "- TASK-050 — first\n"
            "- TASK-075 — second\n"
            "- TASK-080 — third\n"
        )
        parsed = parse_task_file(content)
        assert parsed is not None
        assert parsed.dependencies == ["TASK-050", "TASK-075", "TASK-080"]

    def test_front_matter_stripped_before_parse(self) -> None:
        """Parser must tolerate the standard HTML comment header."""
        content = (
            "<!-- domain:DOCS | layer:task | ssot:true | updated:2026-04-06 -->\n"
            "# TASK-050: With front-matter\n\n"
            "## Goal\n\nSomething.\n"
        )
        parsed = parse_task_file(content)
        assert parsed is not None
        assert parsed.task_id == "TASK-050"
