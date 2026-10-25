"""`make memory-lint` keeps .agents/memory indexed and inside what Claude Code loads.

Spec: src/core/rules/memory.md § Enforcement.
"""

from __future__ import annotations

import datetime
import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "src/core/scripts/memory_lint.py"
_SPEC = importlib.util.spec_from_file_location("memory_lint", SCRIPT)
assert _SPEC and _SPEC.loader
memory_lint = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(memory_lint)

STAGED_INDEX = [memory_lint.INDEX_PATH]
TODAY = datetime.date(2026, 10, 24)
MAIN = (
    "# Memory Index\n\n- [A](a.md) — rule a\n- [Media](index-media.md) — open before media work\n"
)
MEDIA = "# Media\n\n- [B](b.md) — recipe b\n"


def _index_line(total_bytes: int, filler: str = "x") -> str:
    head = "- [Title](title.md) — "
    room = total_bytes - len(head.encode("utf-8"))
    return head + filler * (room // len(filler.encode("utf-8")))


def _body(kind: str, verified: str | None = None) -> str:
    extra = f"\n  verified: {verified}" if verified else ""
    return f"---\nname: m\nmetadata:\n  type: {kind}{extra}\n---\n\nBody.\n"


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    memory_dir = tmp_path / ".agents" / "memory"
    memory_dir.mkdir(parents=True)
    for name, text in files.items():
        (memory_dir / name).write_text(text, encoding="utf-8")
    return tmp_path


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_line_at_the_cap_passes() -> None:
    text = _index_line(memory_lint.INDEX_LINE_MAX_BYTES) + "\n"
    assert memory_lint.long_index_line_warnings(text, STAGED_INDEX) == []


def test_line_one_byte_over_the_cap_names_its_line() -> None:
    text = "# Memory Index\n\n" + _index_line(memory_lint.INDEX_LINE_MAX_BYTES + 1) + "\n"
    warnings = memory_lint.long_index_line_warnings(text, STAGED_INDEX)
    assert len(warnings) == 1 and "MEMORY.md:3:" in warnings[0]


def test_cap_counts_bytes_not_characters() -> None:
    line = _index_line(memory_lint.INDEX_LINE_MAX_BYTES + 3, filler="—")
    assert len(line) <= memory_lint.INDEX_LINE_MAX_BYTES
    assert len(memory_lint.long_index_line_warnings(line, STAGED_INDEX)) == 1


def test_long_lines_are_asked_only_when_the_index_is_staged() -> None:
    text = _index_line(memory_lint.INDEX_LINE_MAX_BYTES + 50)
    assert memory_lint.long_index_line_warnings(text, ["docs/x.md"]) == []


def test_memories_reach_through_one_level_and_have_one_owner() -> None:
    errors, owners = memory_lint.link_structure(MAIN, {"index-media": MEDIA}, {"a", "b"})
    assert errors == []
    assert owners == {"a": "MEMORY", "b": "index-media"}


def test_sub_index_that_main_does_not_link_reaches_nothing() -> None:
    errors, _ = memory_lint.link_structure("- [A](a.md) — a\n", {"index-media": MEDIA}, {"a", "b"})
    assert any("index-media.md is not linked from MEMORY.md" in e for e in errors)
    assert any(e.startswith("b.md exists but no index links it") for e in errors)


def test_memory_linked_from_two_indexes_fails() -> None:
    main = MAIN + "- [B again](b.md) — dup\n"
    errors, _ = memory_lint.link_structure(main, {"index-media": MEDIA}, {"a", "b"})
    assert any("b.md is linked from MEMORY and index-media" in e for e in errors)


def test_sub_indexes_do_not_nest() -> None:
    subs = {
        "index-media": MEDIA + "- [More](index-more.md) — deeper\n",
        "index-more": "- [C](c.md) — c\n",
    }
    errors, _ = memory_lint.link_structure(MAIN, subs, {"a", "b", "c"})
    assert any("sub-indexes are one level" in e for e in errors)


def test_dangling_index_line_fails() -> None:
    errors, _ = memory_lint.link_structure(
        MAIN + "- [Gone](gone.md) — moved\n", {"index-media": MEDIA}, {"a", "b"}
    )
    assert any("MEMORY.md links gone.md" in e for e in errors)


def test_status_word_in_the_rule_fails_but_not_in_the_title_or_a_compound() -> None:
    assert len(memory_lint.status_errors("index-media.md", "- [B](b.md) — still broken\n")) == 1
    assert memory_lint.status_errors("MEMORY.md", "- [Not done until green](x.md) — run it\n") == []
    assert (
        memory_lint.status_errors("MEMORY.md", "- [X](x.md) — --no-verify is hook-blocked\n") == []
    )


def test_staged_body_is_asked_for_the_index_that_owns_it() -> None:
    owners = {"a": "MEMORY", "b": "index-media"}
    staged = [".agents/memory/b.md", memory_lint.INDEX_PATH]
    warnings = memory_lint.unreviewed_index_warnings(staged, owners)
    assert len(warnings) == 1 and "without index-media.md" in warnings[0]
    staged.append(".agents/memory/index-media.md")
    assert memory_lint.unreviewed_index_warnings(staged, owners) == []


def test_feedback_and_user_memories_need_no_verified_date() -> None:
    assert memory_lint.verification_findings("m", _body("feedback"), TODAY) == ([], [])
    assert memory_lint.verification_findings("m", _body("user"), TODAY) == ([], [])


def test_project_memory_without_a_date_warns_with_todays_date() -> None:
    errors, warnings = memory_lint.verification_findings("m", _body("project"), TODAY)
    assert errors == [] and "verified: 2026-10-24" in warnings[0]


def test_verified_date_window() -> None:
    assert memory_lint.verification_findings("m", _body("project", "2026-07-26"), TODAY) == ([], [])
    _, warnings = memory_lint.verification_findings("m", _body("project", "2026-07-25"), TODAY)
    assert "91 days ago" in warnings[0]
    assert memory_lint.verification_findings("m", _body("reference", '"2026-10-20"'), TODAY) == (
        [],
        [],
    )


def test_malformed_or_future_verified_date_fails() -> None:
    assert (
        len(memory_lint.verification_findings("m", _body("project", "24/10/2026"), TODAY)[0]) == 1
    )
    assert (
        len(memory_lint.verification_findings("m", _body("project", "2026-11-01"), TODAY)[0]) == 1
    )


def test_index_over_the_byte_limit_fails_and_near_it_warns() -> None:
    errors, warnings = memory_lint.index_size_findings("x" * 23_000)
    assert errors == [] and len(warnings) == 1
    errors, _ = memory_lint.index_size_findings("x" * (memory_lint.INDEX_MAX_BYTES + 1))
    assert len(errors) == 1


def test_index_over_200_lines_fails() -> None:
    errors, _ = memory_lint.index_size_findings("- line\n" * (memory_lint.INDEX_MAX_LINES + 1))
    assert len(errors) == 1 and "lines" in errors[0]


def test_cli_passes_a_clean_corpus(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        {"MEMORY.md": MAIN, "index-media.md": MEDIA, "a.md": "A, see [[b]].\n", "b.md": "B.\n"},
    )
    result = _run(root)
    assert result.returncode == 0, result.stdout
    assert "[OK] memory-lint: 2 memories, 1 sub-indexes, 2 indexed, 1 wikilinks" in result.stdout


def test_cli_fails_on_an_unindexed_memory_and_names_the_rerun(tmp_path: Path) -> None:
    root = _project(
        tmp_path, {"MEMORY.md": "- [A](a.md) — rule a\n", "a.md": "A\n", "orphan.md": "O\n"}
    )
    result = _run(root)
    assert result.returncode == 1
    assert "[FAIL] orphan.md exists but no index links it" in result.stdout
    assert "rerun: make memory-lint" in result.stdout


def test_cli_fails_on_a_broken_wikilink(tmp_path: Path) -> None:
    root = _project(tmp_path, {"MEMORY.md": "- [A](a.md) — rule a\n", "a.md": "See [[gone]].\n"})
    result = _run(root)
    assert result.returncode == 1 and "[[gone]] resolves to no memory" in result.stdout


def test_cli_skips_a_project_without_memory_and_fails_without_an_index(tmp_path: Path) -> None:
    assert "[SKIP]" in _run(tmp_path).stdout
    (tmp_path / ".agents" / "memory").mkdir(parents=True)
    result = _run(tmp_path)
    assert result.returncode == 1 and "MEMORY.md is missing" in result.stdout
