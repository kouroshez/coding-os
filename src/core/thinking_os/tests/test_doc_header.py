"""Tests for header-only doc parsing (TASK-155)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.docs import list_doc_headers, parse_doc_header


def _write(tmp_path: Path, name: str, body: str) -> Path:
    target = tmp_path / name
    target.write_text(body, encoding="utf-8")
    return target


def test_parse_long_form_opening_block(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "long.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 -->
# Long Form Example

Purpose: One-sentence purpose.
Read when: A specific trigger condition.
Skip when: Inverse condition.
Read next: [a.md](a.md), [b.md](b.md)

> Nav: irrelevant
""",
    )
    header = parse_doc_header(target)
    assert header is not None
    assert header["title"] == "Long Form Example"
    assert header["frontmatter"]["domain"] == "DOCS"
    assert header["frontmatter"]["layer"] == "policy"
    assert header["frontmatter"]["ssot"] == "true"
    assert header["frontmatter"]["updated"] == "2026-04-28"
    ob = header["opening_block"]
    assert ob["purpose"] == "One-sentence purpose."
    assert ob["read_when"] == "A specific trigger condition."
    assert ob["skip_when"] == "Inverse condition."
    assert ob["read_next"] == "[a.md](a.md), [b.md](b.md)"
    assert header["header_token_estimate"] >= 1


def test_parse_short_form_opening_block(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "short.md",
        """\
<!-- domain:BACKEND | layer:playbook | ssot:ref | updated:2026-04-28 | tokens:900 -->
# Short Form Example

> P: Compressed purpose.
> R: trigger.
> S: do not.
> N: ../foo.md
""",
    )
    header = parse_doc_header(target)
    assert header is not None
    assert header["frontmatter"]["domain"] == "BACKEND"
    assert header["frontmatter"]["tokens"] == 900
    ob = header["opening_block"]
    assert ob["purpose"] == "Compressed purpose."
    assert ob["read_when"] == "trigger."
    assert ob["skip_when"] == "do not."
    assert ob["read_next"] == "../foo.md"


def test_parse_reads_list(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "with-reads.md",
        """\
<!-- domain:CORE | layer:reference | ssot:true | updated:2026-04-28 | reads:[a.md, b.md, c.md] -->
# Reads Vector
""",
    )
    header = parse_doc_header(target)
    assert header is not None
    assert header["frontmatter"]["reads"] == ["a.md", "b.md", "c.md"]


def test_parse_missing_frontmatter(tmp_path: Path) -> None:
    target = _write(tmp_path, "no-fm.md", "# Just a title\n\nplain prose.\n")
    header = parse_doc_header(target)
    assert header is not None
    assert header["frontmatter"] == {}
    assert header["title"] == "Just a title"


def test_parse_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "does-not-exist.md"
    assert parse_doc_header(target) is None


def test_parse_long_form_wins_over_short(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "both.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 -->
# Both Forms

> P: short purpose.
> R: short read-when.

Purpose: long purpose.
Read when: long read-when.
Skip when: long skip-when.
Read next: long read-next.
""",
    )
    header = parse_doc_header(target)
    assert header is not None
    ob = header["opening_block"]
    assert ob["purpose"] == "long purpose."
    assert ob["read_when"] == "long read-when."


def test_list_doc_headers_filters(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "p1.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 -->
# Policy 1

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
    )
    _write(
        tmp_path,
        "p2.md",
        """\
<!-- domain:DOCS | layer:reference | ssot:ref | updated:2026-03-01 -->
# Reference

Purpose: y.
Read when: y.
Skip when: y.
Read next: y.
""",
    )
    _write(
        tmp_path,
        "p3.md",
        """\
<!-- domain:BACKEND | layer:policy | ssot:true | updated:2026-04-28 -->
# Backend Policy

Purpose: z.
Read when: z.
Skip when: z.
Read next: z.
""",
    )
    # Domain filter.
    rows = list_doc_headers(tmp_path, domain="DOCS")
    assert len(rows) == 2

    # Layer filter combined.
    only_policy = list_doc_headers(tmp_path, domain="DOCS", layer="policy")
    assert len(only_policy) == 1
    assert only_policy[0]["title"] == "Policy 1"

    # ssot filter.
    only_ref = list_doc_headers(tmp_path, ssot="ref")
    assert len(only_ref) == 1
    assert only_ref[0]["title"] == "Reference"

    # since_iso filter.
    fresh = list_doc_headers(tmp_path, since_iso="2026-04-01")
    assert len(fresh) == 2  # p1 + p3
    assert all(r["frontmatter"]["updated"] >= "2026-04-01" for r in fresh)


def test_list_doc_headers_skips_malformed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "good.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 -->
# Good

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
    )
    _write(tmp_path, "no-fm.md", "# Just title\n\nbody only\n")
    rows = list_doc_headers(tmp_path)
    titles = {r["title"] for r in rows}
    assert "Good" in titles
    assert "Just title" not in titles


def test_list_doc_headers_limit(tmp_path: Path) -> None:
    for i in range(5):
        _write(
            tmp_path,
            f"file-{i}.md",
            f"""\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-{20 + i:02d} -->
# Doc {i}

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
        )
    rows = list_doc_headers(tmp_path, limit=3)
    assert len(rows) == 3


def test_list_doc_headers_sort_priority_then_updated(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "low.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 | priority:0.1 -->
# Low

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
    )
    _write(
        tmp_path,
        "high.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-03-01 | priority:0.9 -->
# High

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
    )
    rows = list_doc_headers(tmp_path)
    assert [r["title"] for r in rows] == ["High", "Low"]


def test_list_doc_headers_limit_keeps_top_priority(tmp_path: Path) -> None:
    # Regression (TASK-137): the limit must apply AFTER the priority sort, not
    # mid-walk — otherwise the returned top-N is rglob (filesystem) order.
    for i in range(5):
        _write(
            tmp_path,
            f"doc-{i}.md",
            f"""\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-01 | priority:0.1 -->
# Filler {i}

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
        )
    _write(
        tmp_path,
        "winner.md",
        """\
<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-01 | priority:0.9 -->
# Winner

Purpose: x.
Read when: x.
Skip when: x.
Read next: x.
""",
    )
    rows = list_doc_headers(tmp_path, limit=1)
    assert len(rows) == 1
    assert rows[0]["title"] == "Winner"


def test_parse_handles_binary(tmp_path: Path) -> None:
    target = tmp_path / "image.md"
    target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    header = parse_doc_header(target)
    # Binary parses to "no frontmatter / no opening block"; not crash.
    assert header is not None
    assert header["frontmatter"] == {}
    assert header["opening_block"] == {}
