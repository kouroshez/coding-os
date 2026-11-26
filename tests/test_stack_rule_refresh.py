"""Stack rules are linked: an untouched one follows its template, an edit stays.

Spec: docs/engineering/hub-architecture.md (stack rules are linked like core
rules). Fixtures link a throwaway install under tmp_path, never src/templates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli import _localize_links as localize_mod
from cli._localize_links import delocalize, localize
from cli._update_manifest import TEMPLATES_DIR, _scan_project_assets
from cli.update import _retire_template_mirror

RULE = ".claude/rules/demo-backend.md"


@pytest.fixture()
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "install"
    template = root / "templates" / "demo" / "rules" / "backend.md"
    template.parent.mkdir(parents=True)
    template.write_text("template v1\n", encoding="utf-8")
    roots = {"core": root.resolve(), "library": (tmp_path / "library").resolve()}
    monkeypatch.setattr(localize_mod, "_roots", lambda: roots)

    class _Stack:
        source_dir = root / "templates" / "demo"

    monkeypatch.setattr("cli._init_registries._get_stack_registry", lambda: {"demo": _Stack()})
    monkeypatch.setattr(
        "cli._resources.templates_dir", lambda *parts: root.joinpath("templates", *parts)
    )
    return root


@pytest.fixture()
def project(tmp_path: Path, install: Path) -> Path:
    project = tmp_path / "project"
    (project / ".coding-os").mkdir(parents=True)
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / RULE).symlink_to(install / "templates" / "demo" / "rules" / "backend.md")
    localize(project, ["claude"])
    return project


def test_a_linked_stack_rule_becomes_a_managed_copy(project: Path) -> None:
    rule = project / RULE
    assert not rule.is_symlink() and rule.read_text(encoding="utf-8") == "template v1\n"
    entry = localize_mod._load_manifest(project)[RULE]
    assert (entry["kind"], entry["source"]) == ("copy", "templates/demo/rules/backend.md")


def test_an_untouched_rule_follows_its_template(project: Path, install: Path) -> None:
    (install / "templates" / "demo" / "rules" / "backend.md").write_text("template v2\n")

    delocalize(project)
    localize(project, ["claude"])

    assert (project / RULE).read_text(encoding="utf-8") == "template v2\n"


def test_an_edited_rule_stays_the_projects(project: Path, install: Path) -> None:
    (project / RULE).write_text("my rule\n", encoding="utf-8")
    (install / "templates" / "demo" / "rules" / "backend.md").write_text("template v2\n")

    kept = delocalize(project)
    localize(project, ["claude"])

    assert kept == [RULE]
    assert (project / RULE).read_text(encoding="utf-8") == "my rule\n"


def test_update_never_adds_or_prunes_a_stack_rule(tmp_path: Path) -> None:
    """A missing stack rule may have been deleted on purpose; a present one is not an orphan."""
    project = tmp_path / "project"
    (project / ".claude" / "rules").mkdir(parents=True)
    source = next((TEMPLATES_DIR / "fastapi" / "rules").glob("*.md"))
    (project / ".claude" / "rules" / f"fastapi-{source.name}").symlink_to(source)

    present = _scan_project_assets(project, ["rules"], "claude")

    assert f"fastapi-{source.name}" not in present["rules"]


@pytest.fixture()
def legacy(tmp_path: Path, install: Path) -> Path:
    """An install from before linking: a plain copy plus the byte-exact mirror."""
    project = tmp_path / "legacy"
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / RULE).write_text("template v1\n", encoding="utf-8")
    mirror = project / ".coding-os" / "src" / "templates" / "demo" / "rules" / "backend.md"
    mirror.parent.mkdir(parents=True)
    mirror.write_text("template v1\n", encoding="utf-8")
    (install / "templates" / "demo" / "rules" / "backend.md").write_text("template v2\n")
    return project


def test_an_untouched_legacy_copy_is_linked_and_the_mirror_goes(legacy: Path) -> None:
    assert _retire_template_mirror(legacy, ["demo"], ["claude"], dry_run=False, report=False)

    assert (legacy / RULE).is_symlink()
    assert (legacy / RULE).read_text(encoding="utf-8") == "template v2\n"
    assert not (legacy / ".coding-os" / "src").exists()


def test_an_edited_legacy_copy_stays(legacy: Path) -> None:
    (legacy / RULE).write_text("my rule\n", encoding="utf-8")

    _retire_template_mirror(legacy, ["demo"], ["claude"], dry_run=False, report=False)

    assert not (legacy / RULE).is_symlink()
    assert (legacy / RULE).read_text(encoding="utf-8") == "my rule\n"


def test_a_dry_run_changes_nothing(legacy: Path) -> None:
    assert _retire_template_mirror(legacy, ["demo"], ["claude"], dry_run=True, report=False)

    assert not (legacy / RULE).is_symlink()
    assert (legacy / ".coding-os" / "src").is_dir()


def test_no_mirror_means_nothing_to_retire(project: Path) -> None:
    assert not _retire_template_mirror(project, ["demo"], ["claude"], dry_run=False, report=False)


def test_a_managed_stack_rule_copy_is_never_pruned_by_update(tmp_path: Path) -> None:
    from cli._managed_manifest import _digest

    project = tmp_path / "project"
    rule = project / ".claude" / "rules" / "fastapi-backend.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("managed copy\n", encoding="utf-8")
    entry = {"root": "core", "source": "templates/fastapi/rules/backend.md", "kind": "copy"}
    manifest = {"version": 1, "entries": {".claude/rules/fastapi-backend.md": entry}}
    entry["sha256"] = _digest(rule)
    (project / ".coding-os").mkdir()
    (project / ".coding-os" / "managed-files.json").write_text(json.dumps(manifest))

    present = _scan_project_assets(project, ["rules"], "claude")

    assert "fastapi-backend.md" not in present["rules"]


def test_an_overlay_stack_rule_is_copied_not_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link into ~/.coding-os/templates would dangle in every other clone."""
    from cli import _init_scaffold

    overlay = tmp_path / "home" / ".coding-os" / "templates" / "mine"
    (overlay / "rules").mkdir(parents=True)
    (overlay / "rules" / "backend.md").write_text("overlay rule\n", encoding="utf-8")

    class _Stack:
        source_dir = overlay

    monkeypatch.setattr(_init_scaffold, "_get_stack_registry", lambda: {"mine": _Stack()})
    project = tmp_path / "project"
    project.mkdir()

    _init_scaffold._apply_template("mine", project, agent="claude")

    rule = project / ".claude" / "rules" / "mine-backend.md"
    assert not rule.is_symlink() and rule.read_text(encoding="utf-8") == "overlay rule\n"


def test_a_legacy_overlay_rule_copy_stays_a_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = tmp_path / "home" / ".coding-os" / "templates" / "mine"
    (overlay / "rules").mkdir(parents=True)
    (overlay / "rules" / "backend.md").write_text("overlay rule\n", encoding="utf-8")

    class _Stack:
        source_dir = overlay

    monkeypatch.setattr("cli._init_registries._get_stack_registry", lambda: {"mine": _Stack()})
    project = tmp_path / "legacy"
    rule = project / ".claude" / "rules" / "mine-backend.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("overlay rule\n", encoding="utf-8")
    (project / ".coding-os" / "src" / "templates" / "mine" / "rules").mkdir(parents=True)

    _retire_template_mirror(project, ["mine"], ["claude"], dry_run=False, report=False)

    assert not rule.is_symlink() and rule.read_text(encoding="utf-8") == "overlay rule\n"


def test_cos_update_keeps_an_untouched_rule_managed_and_an_edited_one(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from cli.main import cli

    project = tmp_path / "proj"
    init = [
        "init",
        "-a",
        "claude",
        "-t",
        "fastapi",
        "-d",
        str(project),
        "--no-index",
        "--no-register",
    ]
    assert CliRunner().invoke(cli, init).exit_code == 0
    rule = project / ".claude" / "rules" / "fastapi-backend.md"
    before = rule.read_text(encoding="utf-8")

    assert CliRunner().invoke(cli, ["update", "-d", str(project)]).exit_code == 0
    assert rule.read_text(encoding="utf-8") == before
    assert (
        localize_mod._load_manifest(project)[".claude/rules/fastapi-backend.md"]["kind"] == "copy"
    )

    rule.write_text("my rule\n", encoding="utf-8")
    assert CliRunner().invoke(cli, ["update", "-d", str(project)]).exit_code == 0
    assert rule.read_text(encoding="utf-8") == "my rule\n"
