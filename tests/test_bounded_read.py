"""Bounded tail-read helpers for observability/cognition routes (TASK-225)."""

from __future__ import annotations

import os

from web.routes._bounded_read import newest_files, tail_lines, tail_text


def test_tail_text_small_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("hello\nworld\n")
    assert tail_text(p) == "hello\nworld\n"


def test_tail_text_bounds_large_file(tmp_path):
    p = tmp_path / "big.txt"
    p.write_bytes(b"x" * (1024 * 1024))  # 1 MB on disk
    out = tail_text(p, max_bytes=64 * 1024)
    assert len(out) == 64 * 1024  # only the tail window was read, not 1 MB


def test_tail_lines_small_not_truncated(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text("a\nb\nc\n")
    lines, truncated = tail_lines(p)
    assert lines == ["a", "b", "c"]
    assert truncated is False


def test_tail_lines_truncated_drops_partial_head(tmp_path):
    p = tmp_path / "big.jsonl"
    p.write_text("\n".join(f"line{i:06d}" for i in range(100_000)) + "\n")
    lines, truncated = tail_lines(p, max_bytes=4096)
    assert truncated is True
    assert lines[-1] == "line099999"  # newest line preserved
    assert len(lines) < 1000  # bounded to the window, not all 100k lines


def test_tail_lines_max_lines_caps(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text("\n".join(str(i) for i in range(500)) + "\n")
    lines, truncated = tail_lines(p, max_lines=10)
    assert lines == [str(i) for i in range(490, 500)]
    assert truncated is True


def test_tail_lines_missing_file(tmp_path):
    lines, truncated = tail_lines(tmp_path / "nope.txt")
    assert lines == []
    assert truncated is False


def test_newest_files_by_mtime(tmp_path):
    for i in range(5):
        p = tmp_path / f"t{i}.jsonl"
        p.write_text("x")
        os.utime(p, (1000 + i, 1000 + i))
    newest = newest_files(tmp_path, "*.jsonl", 3)
    assert [p.name for p in newest] == ["t4.jsonl", "t3.jsonl", "t2.jsonl"]


def test_newest_files_unbounded_when_limit_zero(tmp_path):
    for i in range(4):
        (tmp_path / f"t{i}.jsonl").write_text("x")
    assert len(newest_files(tmp_path, "*.jsonl", 0)) == 4
