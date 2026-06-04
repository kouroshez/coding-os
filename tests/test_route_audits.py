"""Regression tests for src/core/web/routes/audits.py — pin the markdown
+ YAML status parsers + row counters so the Hub UI surfaces correct
state for both audit conventions.

Pre-fix bugs:
  1. _parse_frontmatter only handled YAML `---` frontmatter → audits
     using markdown-bold `**Status:** in_progress` form (TASK-029,
     TASK-032 graph-os audits) returned status="unknown".
  2. _row_counts regex required first cell to be JUST `T1` / `G10` →
     tables with `| F1/#2 resolve column-order |` rows counted as 0.
  3. Checklist-shaped audits with `- [x]` checkboxes (no `|` table
     rows) showed no progress signal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CORE = Path(__file__).resolve().parents[1] / "src" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from web.routes.audits import (  # noqa: E402 — sys.path mutation above
    AUDIT_STATUS_VALUES,
    _canonical_status,
    _parse_frontmatter,
    _row_counts,
)


class TestParseFrontmatter:
    def test_yaml_frontmatter_canonical(self):
        text = (
            "---\n"
            "audit_id: foo-2026-01-01\n"
            "task_id: TASK-100\n"
            "status: in_progress\n"
            "predicates: [counts_after_zero, reviewer_pass]\n"
            "---\n"
            "# body\n"
        )
        fm = _parse_frontmatter(text)
        assert fm["audit_id"] == "foo-2026-01-01"
        assert fm["task_id"] == "TASK-100"
        assert fm["status"] == "in_progress"
        assert fm["predicates"] == ["counts_after_zero", "reviewer_pass"]

    def test_markdown_bold_form_status(self):
        """Bug 1: historic audits use `**Status:** X` on the second
        line. Parser must surface the same status the agent banner sees."""
        text = (
            "# Audit — Graph OS Deep (2026-05-25)\n\n"
            "**Task:** TASK-032 · **Status:** in_progress\n"
            "**Trigger:** user exhaustive intent\n"
        )
        fm = _parse_frontmatter(text)
        assert fm["status"] == "in_progress"
        assert fm["task_id"] == "TASK-032"

    def test_markdown_bold_strips_parenthetical(self):
        """`**Status:** complete (all 14 fixes landed ...)` — keep the
        canonical state, drop the prose elaboration."""
        text = (
            "# Audit — Foo\n\n"
            "**Task:** TASK-029\n"
            "**Status:** complete (all 14 fixes landed + 15 regression tests)\n"
        )
        fm = _parse_frontmatter(text)
        assert fm["status"] == "complete"
        assert fm["task_id"] == "TASK-029"

    def test_yaml_wins_over_markdown(self):
        """YAML frontmatter is canonical — markdown body must not
        overwrite a key the YAML already set."""
        text = "---\nstatus: completed\n---\n# Body\n\n**Status:** in_progress\n"
        fm = _parse_frontmatter(text)
        assert fm["status"] == "completed"

    def test_bold_severity_in_tables_ignored(self):
        """Bug 1 root cause: regex picked up `**CRITICAL**` cells in the
        defect tables. Only scan the doc header (first 30 lines)."""
        body_lines = ["| **CRITICAL** | resolve | description |"] * 50
        text = "# Audit\n\n**Status:** in_progress\n\n## Defects\n\n" + "\n".join(body_lines) + "\n"
        fm = _parse_frontmatter(text)
        # No spurious "critical" key — only header keys land.
        assert "critical" not in fm
        assert fm["status"] == "in_progress"


class TestRowCounts:
    def test_simple_numeric_ids(self):
        text = "| # | Sev |\n|---|---|\n| 1 | high |\n| 2 | low |\n"
        c = _row_counts(text)
        assert c["total"] == 2

    def test_prefixed_ids(self):
        text = "| # | Sev |\n|---|---|\n| G10 | high |\n| L1 | low |\n"
        c = _row_counts(text)
        assert c["total"] == 2

    def test_prefixed_with_summary_text(self):
        """Bug 2: deep-audit rows like `| F1/#2 resolve column-order |`
        used to count as 0 because regex required first cell to be JUST
        the ID. Relaxed pattern accepts trailing prose."""
        text = (
            "| F# / # | Status | Note |\n"
            "|---|---|---|\n"
            "| F1/#2 resolve column-order | HOLDS | aligned |\n"
            "| F2/#6 rename_plan kinds | HOLDS | _BEHAVIOURAL_EDGE_TYPES SSOT |\n"
        )
        c = _row_counts(text)
        assert c["total"] == 2

    def test_checkboxes_counted_as_rows(self):
        """Bug 3: checklist-shaped audits (no tables) had rows_total=0
        so the Hub UI showed no progress bar. Count `- [x]` / `- [ ]`."""
        text = (
            "# Fix Checklist\n\n"
            "- [x] F1 done\n"
            "- [x] F2 done\n"
            "- [ ] F3 pending\n"
            "- [ ] F4 pending\n"
            "- [ ] F5 pending\n"
        )
        c = _row_counts(text)
        assert c["total"] == 5
        assert c["unchecked"] == 3

    def test_mixed_table_plus_checkboxes(self):
        text = "| 1 | row |\n| 2 | row |\n- [x] done\n- [ ] pending\n"
        c = _row_counts(text)
        assert c["total"] == 4
        assert c["unchecked"] == 1

    def test_header_rows_not_counted(self):
        text = "| # | Sev | Notes |\n|---|---|---|\n"
        c = _row_counts(text)
        assert c["total"] == 0

    def test_deferred_section_checkboxes_excluded(self):
        """Closed audits often carry a `## Deferred` section listing
        explicit non-work. Those `- [ ]` items must NOT count as gaps
        because they're already-decided deferrals, not unfinished
        commitments."""
        text = (
            "## Wave 1\n\n"
            "- [x] F1 done\n"
            "- [x] F2 done\n\n"
            "## Deferred (separate task)\n\n"
            "- [ ] F15 path weighting · DEFER\n"
            "- [ ] F16 doc-only · DEFER\n"
            "- [ ] F17 icebox · DEFER\n\n"
            "## Commit policy\n\n"
            "One fix → one commit.\n"
        )
        c = _row_counts(text)
        assert c["total"] == 2
        assert c["unchecked"] == 0

    def test_skipped_section_also_excluded(self):
        text = "## Active\n\n- [x] A done\n- [ ] B pending\n\n## Skipped\n\n- [ ] X out-of-scope\n"
        c = _row_counts(text)
        assert c["total"] == 2
        assert c["unchecked"] == 1  # only B from Active

    def test_non_work_section_ends_at_next_heading(self):
        """Skip block must terminate at the next same-depth heading so
        later sections still count."""
        text = "## Deferred\n\n- [ ] dropped\n\n## Open work\n\n- [ ] still-pending\n"
        c = _row_counts(text)
        assert c["total"] == 1
        assert c["unchecked"] == 1


class TestStatusEnum:
    """Status field must be a controlled enum — free-form drift produced
    `complete` (typo) vs `completed` (canonical) in the wild. The
    canonicaliser maps known aliases to the SSOT enum + everything else
    to `unknown` so consumers see consistent labels."""

    def test_canonical_completed_passes(self):
        assert _canonical_status("completed") == "completed"
        assert _canonical_status("in_progress") == "in_progress"
        assert _canonical_status("cancelled") == "cancelled"

    def test_legacy_complete_typo_normalises_to_completed(self):
        """Historic agents wrote `complete` (English adjective) — the
        canonicaliser maps it to the past-tense canonical form."""
        assert _canonical_status("complete") == "completed"
        assert _canonical_status("done") == "completed"

    def test_unknown_value_returns_unknown(self):
        # Free-form prose like "complete (with caveats)" — anything
        # outside the alias map drops to unknown so the UI displays a
        # warning glyph instead of pretending it's real.
        assert _canonical_status("nearly_done") == "unknown"
        assert _canonical_status("wip-mostly") == "unknown"
        assert _canonical_status(None) == "unknown"
        assert _canonical_status("") == "unknown"

    def test_case_insensitive_normalisation(self):
        assert _canonical_status("COMPLETED") == "completed"
        assert _canonical_status("In_Progress") == "in_progress"

    def test_status_raw_preserved_in_scan(self):
        """API surfaces both the canonical value AND the raw input so
        humans + linters can flag drift."""
        from web.routes.audits import _scan_audits

        audits = {a["audit_id"]: a for a in _scan_audits()}
        for a in audits.values():
            assert "status_raw" in a
            # raw should match the original file content (possibly with
            # surrounding whitespace) — at minimum, when canonical is a
            # real value the raw must be non-empty.
            if a["status"] in AUDIT_STATUS_VALUES:
                assert a["status_raw"]

    def test_enum_values_locked(self):
        # Lock the enum — adding a new value must be deliberate (failing
        # test signals intent + code review).
        assert AUDIT_STATUS_VALUES == ("in_progress", "completed", "cancelled")


class TestPromptLeakDetection:
    """matched_exhaustive must hold ONLY canonical vocabulary tokens
    (from extract_intent.py). Hand-edited audits sometimes capture
    full prompt sentences — that is private user input, not metadata.

    Heuristic: any token containing whitespace OR longer than the
    longest known vocabulary entry (`down to the last one` = 20 chars)
    is almost certainly a quoted prompt fragment, not a token.
    """

    @staticmethod
    def _looks_like_prompt_quote(tok: str) -> bool:
        # Vocabulary tokens are single words or up to 4-word phrases
        # under ~20 chars. Anything bigger = prompt quote.
        if len(tok) > 24:
            return True
        # Persian sentences typically include verbs ending in را / رو / ها
        # plus multiple words. Bare vocabulary tokens are usually 1-2 words.
        if tok.count(" ") >= 3:
            return True
        return False

    def test_live_graph_os_audits_have_no_prompt_quotes(self):
        """End-to-end: after migration the 3 graph-os audits must not
        contain full Persian sentences in matched_exhaustive."""
        from web.routes.audits import _scan_audits

        audits = {a["audit_id"]: a for a in _scan_audits()}
        for slug in (
            "graph-os-deep-2026-05-25",
            "graph-os-exhaustive-2026-05-24",
            "graph-os-fix-checklist-2026-05-24",
        ):
            if slug not in audits:
                continue
            for tok in audits[slug].get("matched_exhaustive", []) or []:
                assert not self._looks_like_prompt_quote(tok), (
                    f"prompt-quote leaked in {slug}: {tok!r}"
                )

    def test_quote_heuristic_catches_known_bad_examples(self):
        bad = "کل سیستم graph رو تست و بنچ مارک بگیری"
        assert self._looks_like_prompt_quote(bad)
        worse = "تا اخرین بخش گراف دیپ شد"
        assert self._looks_like_prompt_quote(worse)

    def test_quote_heuristic_passes_known_good_tokens(self):
        for tok in ("همه", "تمامی", "صد در صد", "all", "comprehensive", "100%"):
            assert not self._looks_like_prompt_quote(tok), tok


def test_scan_audits_surfaces_real_status_for_graph_os_deep():
    """End-to-end: the live audit-graph-os-deep-2026-05-25.md must
    surface a real status (not 'unknown'). Concrete value depends on
    whether the audit was closed; assert any non-unknown state."""
    from web.routes.audits import _scan_audits

    audits = {a["audit_id"]: a for a in _scan_audits()}
    if "graph-os-deep-2026-05-25" not in audits:
        pytest.skip("graph-os-deep audit not present in this checkout")
    status = audits["graph-os-deep-2026-05-25"]["status"]
    assert status != "unknown"
    assert audits["graph-os-deep-2026-05-25"]["task_id"] == "TASK-032"
    assert audits["graph-os-deep-2026-05-25"]["rows_total"] > 0
