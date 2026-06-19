"""Tests for cli.stack_registry — YAML loading, validation, soft-fail semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.stack_registry import (
    StackManifestError,
    load_base_profile,
    load_stack_registry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_stack(base: Path, stack_id: str, extra: str = "") -> Path:
    stack_dir = base / stack_id
    stack_dir.mkdir(parents=True)
    # category: library — neutral category with no conditional substitutions
    # contract (backend/frontend/mobile each require routing+verify keys via
    # the schema allOf). These discovery tests don't assert on category.
    (stack_dir / "stack.yaml").write_text(
        f"version: 1\nid: {stack_id}\nlanguage: python\nlabel: Test Stack\ncategory: library\n{extra}",
        encoding="utf-8",
    )
    return stack_dir


# ---------- live repo ----------


def test_load_live_registry_has_django_and_nextjs() -> None:
    result = load_stack_registry(REPO_ROOT / "src" / "templates")
    assert "django" in result
    assert "nextjs" in result
    assert result["django"].category == "backend"
    assert result["nextjs"].category == "frontend"


def test_load_live_base_profile() -> None:
    base = load_base_profile(REPO_ROOT / "src" / "templates" / "_base")
    assert base.id == "base"
    assert len(base.agents_md_sections) >= 10
    assert "PROJECT_NAME" in base.substitutions


# ---------- invalid YAML → soft fail ----------


def test_invalid_yaml_skipped_with_warning(tmp_path: Path) -> None:
    stack_dir = tmp_path / "brokenstack"
    stack_dir.mkdir()
    (stack_dir / "stack.yaml").write_text(":::\nnot yaml\n[", encoding="utf-8")
    result = load_stack_registry(tmp_path)
    assert "brokenstack" not in result
    assert len(result.warnings) == 1
    assert "brokenstack" in result.warnings[0]


def test_missing_required_field_skipped(tmp_path: Path) -> None:
    stack_dir = tmp_path / "nolabel"
    stack_dir.mkdir()
    (stack_dir / "stack.yaml").write_text(
        "version: 1\nid: nolabel\ncategory: backend\n",  # no label
        encoding="utf-8",
    )
    result = load_stack_registry(tmp_path)
    assert "nolabel" not in result
    assert any("label" in w for w in result.warnings)


def test_mismatched_id_skipped(tmp_path: Path) -> None:
    stack_dir = tmp_path / "actual-name"
    stack_dir.mkdir()
    # category: library so schema validation passes and the loader reaches
    # the dir-name/id mismatch check — that mismatch is what this test asserts.
    (stack_dir / "stack.yaml").write_text(
        "version: 1\nid: wrong-name\nlanguage: python\nlabel: X\ncategory: library\n",
        encoding="utf-8",
    )
    result = load_stack_registry(tmp_path)
    assert "actual-name" not in result
    assert "wrong-name" not in result
    assert any("directory name" in w for w in result.warnings)


def test_unsupported_version_skipped(tmp_path: Path) -> None:
    stack_dir = tmp_path / "oldversion"
    stack_dir.mkdir()
    (stack_dir / "stack.yaml").write_text(
        "version: 999\nid: oldversion\nlabel: X\ncategory: backend\n",
        encoding="utf-8",
    )
    result = load_stack_registry(tmp_path)
    assert "oldversion" not in result


# ---------- multi-stack discovery ----------


def test_multi_stack_discovery(tmp_path: Path) -> None:
    _write_stack(tmp_path, "alpha")
    _write_stack(tmp_path, "beta")
    result = load_stack_registry(tmp_path)
    assert set(result.keys()) == {"alpha", "beta"}


def test_underscore_dirs_ignored(tmp_path: Path) -> None:
    _write_stack(tmp_path, "alpha")
    (tmp_path / "_base").mkdir()
    (tmp_path / "_base" / "stack.yaml").write_text(
        "version: 1\nid: _base\nlabel: X\ncategory: backend\n"
    )
    result = load_stack_registry(tmp_path)
    assert "alpha" in result
    assert "_base" not in result


def test_empty_dir_returns_empty_registry(tmp_path: Path) -> None:
    result = load_stack_registry(tmp_path)
    assert len(result.stacks) == 0


def test_nonexistent_templates_dir_returns_warning() -> None:
    result = load_stack_registry(Path("/nonexistent/path/that/does/not/exist"))
    assert len(result.stacks) == 0
    assert any("not found" in w for w in result.warnings)


# ---------- base profile errors ----------


def test_missing_base_yaml_raises(tmp_path: Path) -> None:
    with pytest.raises(StackManifestError, match="not found"):
        load_base_profile(tmp_path)


# ---------- JSON schema validation ----------


def test_schema_rejects_invalid_category(tmp_path: Path) -> None:
    stack_dir = tmp_path / "badcat"
    stack_dir.mkdir()
    (stack_dir / "stack.yaml").write_text(
        "version: 1\nid: badcat\nlabel: Bad Category\ncategory: not-a-real-category\n",
        encoding="utf-8",
    )
    result = load_stack_registry(tmp_path)
    assert "badcat" not in result
    assert any("category" in w for w in result.warnings)


def test_schema_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    stack_dir = tmp_path / "typo"
    stack_dir.mkdir()
    (stack_dir / "stack.yaml").write_text(
        "version: 1\n"
        "id: typo\n"
        "label: Typo\n"
        "category: backend\n"
        "skillz: [thing]\n",  # typo: should be 'skills'
        encoding="utf-8",
    )
    result = load_stack_registry(tmp_path)
    assert "typo" not in result
    assert any("skillz" in w or "additional" in w.lower() for w in result.warnings)


def test_schema_rejects_bad_ref_code_format(tmp_path: Path) -> None:
    stack_dir = tmp_path / "badref"
    stack_dir.mkdir()
    (stack_dir / "stack.yaml").write_text(
        "version: 1\n"
        "id: badref\n"
        "label: Bad Ref\n"
        "category: backend\n"
        "ref_codes:\n"
        "  - code: not-uppercase\n"  # must match ^REF:[A-Z0-9_-]+$
        "    path: ./foo.md\n"
        "    desc: bad\n",
        encoding="utf-8",
    )
    result = load_stack_registry(tmp_path)
    assert "badref" not in result
    assert any("code" in w or "pattern" in w for w in result.warnings)


def test_schema_accepts_live_stacks() -> None:
    """Sanity: the 4 production stacks must all pass schema validation."""
    result = load_stack_registry(REPO_ROOT / "src" / "templates")
    assert not result.warnings, (
        f"live stacks should all pass schema validation; warnings: {result.warnings}"
    )
    assert len(result.stacks) >= 4


# ---------- out-of-tree community overlay (B-7) ----------


def test_overlay_discovers_community_stack(tmp_path: Path) -> None:
    """A stack in an out-of-tree overlay dir loads alongside the bundled ones —
    a third party adds a stack without forking ($COS_USER_TEMPLATES_DIR)."""
    bundled, overlay = tmp_path / "bundled", tmp_path / "overlay"
    _write_stack(bundled, "alpha")
    _write_stack(overlay, "community-x")
    result = load_stack_registry(bundled, overlay_dirs=(overlay,))
    assert "alpha" in result and "community-x" in result


def test_overlay_may_not_shadow_bundled_stack(tmp_path: Path) -> None:
    """A community stack id that collides with a bundled one is rejected — the
    bundled profile is kept and a warning is recorded."""
    bundled, overlay = tmp_path / "bundled", tmp_path / "overlay"
    _write_stack(bundled, "alpha")  # label "Test Stack"
    (overlay / "alpha").mkdir(parents=True)
    (overlay / "alpha" / "stack.yaml").write_text(
        "version: 1\nid: alpha\nlanguage: python\nlabel: OVERLAY SHADOW\ncategory: library\n",
        encoding="utf-8",
    )
    result = load_stack_registry(bundled, overlay_dirs=(overlay,))
    assert result["alpha"].label == "Test Stack", "bundled stack must win over a community shadow"
    assert any("may not shadow" in w for w in result.warnings)


def test_overlay_defaults_to_env_user_dir(tmp_path: Path, monkeypatch) -> None:
    """With overlay_dirs unset (None), the loader resolves $COS_USER_TEMPLATES_DIR
    so every caller is overlay-aware for free."""
    bundled, overlay = tmp_path / "bundled", tmp_path / "overlay"
    _write_stack(bundled, "alpha")
    _write_stack(overlay, "community-x")
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))
    result = load_stack_registry(bundled)  # default None -> resolves the env dir
    assert "community-x" in result, "default overlay must resolve $COS_USER_TEMPLATES_DIR"
