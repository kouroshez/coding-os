"""TASK-471: the consumer-discovery commands thread the community plugin overlay
($COS_USER_TEMPLATES_DIR / $COS_USER_ADAPTERS_DIR), while the meta-repo SSOT
regen/lint loaders stay bundled-only (the TASK-458 leak guard must not regress).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_STACK_YAML = """\
version: 1
id: {id}
label: "Acme Rust (community)"
category: library
language: rust
"""


def _community_stack(root: Path, stack_id: str) -> Path:
    stack_dir = root / stack_id
    stack_dir.mkdir(parents=True)
    (stack_dir / "stack.yaml").write_text(_STACK_YAML.format(id=stack_id), encoding="utf-8")
    return stack_dir


def test_central_registry_discovers_community_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cos init --template <id>` resolves via main._get_stack_registry()."""
    overlay = tmp_path / "templates"
    _community_stack(overlay, "acme-rust")
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    import cli.main as main

    main._reset_registries_for_tests()
    try:
        registry = main._get_stack_registry()
        assert "acme-rust" in registry  # the repro's "stack not found" is now resolved
    finally:
        main._reset_registries_for_tests()


def test_list_stacks_discovers_community_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = tmp_path / "templates"
    _community_stack(overlay, "acme-rust")
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    from cli._resources import overlay_template_dirs
    from cli.list_stacks import TEMPLATES_DIR
    from cli.stack_registry import load_stack_registry

    registry = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    assert "acme-rust" in registry


def test_add_stack_resolves_community_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """add-stack's registry lookup must find the community id (no hard-abort)."""
    overlay = tmp_path / "templates"
    _community_stack(overlay, "acme-rust")
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    from cli._resources import overlay_template_dirs
    from cli.add_stack import TEMPLATES_DIR
    from cli.stack_registry import load_stack_registry

    registry = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    assert "acme-rust" in registry


def test_ssot_regen_path_stays_bundled_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The leak guard (TASK-458/471): a bundled-only load — exactly what the
    regen/lint/scaffold-SSOT scripts use — must NOT see the community overlay,
    or a community stack would leak into scaffold_manifest.json / dimension-registry.md."""
    overlay = tmp_path / "templates"
    _community_stack(overlay, "acme-rust")
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    from cli._resources import templates_dir
    from cli.stack_registry import load_stack_registry

    bundled_only = load_stack_registry(templates_dir())  # no overlay_dirs = SSOT path
    assert "acme-rust" not in bundled_only


def test_community_id_may_not_shadow_bundled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A community plugin may not shadow a bundled stack — the bundled wins."""
    from cli._resources import templates_dir
    from cli.stack_registry import load_stack_registry

    bundled = load_stack_registry(templates_dir())
    victim = next(iter(bundled.keys()))  # any real bundled stack id

    overlay = tmp_path / "templates"
    shadow = overlay / victim
    shadow.mkdir(parents=True)
    # A deliberately-wrong label so we can prove the bundled profile is the kept one.
    (shadow / "stack.yaml").write_text(
        f'version: 1\nid: {victim}\nlabel: "HIJACKED"\ncategory: library\nlanguage: rust\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    from cli._resources import overlay_template_dirs

    merged = load_stack_registry(templates_dir(), overlay_dirs=overlay_template_dirs())
    assert merged[victim].label != "HIJACKED"  # bundled profile kept on id collision
