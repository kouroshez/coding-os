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


def test_community_scaffold_dir_resolves_from_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-479: config_composer resolves a community stack's scaffold from the
    overlay; a bundled stack still resolves to the bundled tree (no regression)."""
    from cli._resources import templates_dir
    from cli.config_composer import _stack_scaffold_dir

    overlay = tmp_path / "templates"
    (overlay / "acme" / "scaffold" / ".coding-os").mkdir(parents=True)
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    assert _stack_scaffold_dir("acme", templates_dir()) == overlay / "acme" / "scaffold"
    # a real bundled stack is unchanged — bundled-first
    assert _stack_scaffold_dir("python", templates_dir()) == templates_dir() / "python" / "scaffold"


def test_overlay_scaffold_copies_community_stack_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-479: a discovered community stack's scaffold files actually land in
    the project (init/add-stack no longer a silent half-apply)."""
    import cli.main as main

    overlay = tmp_path / "templates"
    _community_stack(overlay, "acme")
    scaffold = overlay / "acme" / "scaffold" / "src"
    scaffold.mkdir(parents=True)
    (scaffold / "ACME.md").write_text("# acme stack file\n", encoding="utf-8")
    monkeypatch.setenv("COS_USER_TEMPLATES_DIR", str(overlay))

    project = tmp_path / "proj"
    project.mkdir()
    main._reset_registries_for_tests()
    try:
        main._overlay_scaffold(project, ("acme",), {})
        assert (project / "src" / "ACME.md").is_file()  # community scaffold landed
    finally:
        main._reset_registries_for_tests()


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
