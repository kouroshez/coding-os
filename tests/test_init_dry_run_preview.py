"""`cos init --dry-run` preview must match what an actual init writes, including
the `<!-- module:X -->` whole-file doc skip the real overlay applies when a
module is disabled (audit INIT-4). Fast (no subprocess) — runs on every PR."""

from __future__ import annotations

from cli.main import _apply_doc_conditions, _scaffold_tree_preview


def test_apply_doc_conditions_skips_whole_file_tagged_doc() -> None:
    """The skip primitive the preview now reuses: a whole-file module tag drops
    the file when its module is off, and is stripped (file kept) when on."""
    doc = "<!-- domain:CORE | module:cognition -->\n# Cognition doc\nbody\n"
    skip_off, _ = _apply_doc_conditions(doc, {"cognition"}, set())
    assert skip_off is True

    skip_on, content = _apply_doc_conditions(doc, set(), set())
    assert skip_on is False
    assert "module:cognition" not in content  # tag stripped, body kept
    assert "Cognition doc" in content


def test_scaffold_preview_accepts_disabled_modules_without_over_including() -> None:
    """Threading disabled_modules into the preview never ADDS paths — a disabled
    module's whole-file-tagged docs can only drop, mirroring the real overlay."""
    base_paths, _ = _scaffold_tree_preview(("python",))
    scoped_paths, _ = _scaffold_tree_preview(("python",), disabled_modules=("graph", "cognition"))
    assert set(scoped_paths) <= set(base_paths)


def test_scaffold_preview_default_is_unchanged() -> None:
    """No disabled modules ⇒ identical to the pre-INIT-4 behaviour (regression)."""
    a, _ = _scaffold_tree_preview(("python",))
    b, _ = _scaffold_tree_preview(("python",), disabled_modules=())
    assert a == b
