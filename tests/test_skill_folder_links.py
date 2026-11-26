"""Whole-folder skill links: Codex lists them, and no step writes through one.

Spec: docs/engineering/skill-architecture.md (whole-folder skill links). Every
fixture links a throwaway install under tmp_path, so a regression here can never
touch the real src/core/skills tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cli import _localize_links as localize_mod
from cli._localize_links import link_form, localize
from cli._resources import core_dir, templates_dir
from cli._skill_project import link_skill_dir, unlink_skill_dir

REPO = Path(__file__).resolve().parents[1]
SKILL_LINK_SH = REPO / "src" / "core" / "scripts" / "_skill_link.sh"


@pytest.fixture()
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "install"
    skill = root / "core" / "skills" / "demo"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("source\n", encoding="utf-8")
    (skill / "references" / "r.md").write_text("ref\n", encoding="utf-8")
    roots = {"core": root.resolve(), "library": (tmp_path / "library").resolve()}
    monkeypatch.setattr(localize_mod, "_roots", lambda: roots)
    monkeypatch.setattr("cli._skill_project.data_root", lambda: root)
    return root


def _shell(function: str, *args: str) -> None:
    script = f'source "{SKILL_LINK_SH}"; {function} "$@"'
    subprocess.run(["bash", "-c", script, "_", *args], check=True, timeout=10)


def test_a_parked_skill_edit_never_writes_through_a_folder_link(
    tmp_path: Path, install: Path
) -> None:
    source = install / "core" / "skills" / "demo"
    project = tmp_path / "project"
    (project / ".coding-os").mkdir(parents=True)
    (project / ".claude" / "skills").mkdir(parents=True)
    (project / ".claude" / "skills" / "demo").symlink_to(source)
    localize(project, ["claude"])
    edited = project / ".claude" / "skills" / "demo" / "SKILL.md"
    edited.write_text("my edit\n", encoding="utf-8")

    with link_form(project, ["claude"]):
        link_skill_dir(project / ".claude" / "skills" / "demo", source)

    assert (source / "SKILL.md").read_text(encoding="utf-8") == "source\n"
    assert edited.read_text(encoding="utf-8") == "my edit\n"


def test_a_users_own_link_with_a_skill_name_is_left_alone(tmp_path: Path, install: Path) -> None:
    mine = tmp_path / "mine" / "demo"
    mine.mkdir(parents=True)
    link = tmp_path / "skills" / "demo"
    link.parent.mkdir()
    link.symlink_to(mine)

    assert link_skill_dir(link, install / "core" / "skills" / "demo") is False
    assert unlink_skill_dir(link) is False
    assert link.resolve() == mine.resolve()


@pytest.mark.parametrize("dest_kind", ["file", "dotdot-named-file"])
def test_the_shell_twin_keeps_a_users_file(tmp_path: Path, install: Path, dest_kind: str) -> None:
    source = install / "core" / "skills" / "demo"
    dest = tmp_path / "skills" / "demo"
    dest.parent.mkdir()
    if dest_kind == "file":
        dest.write_text("mine\n", encoding="utf-8")
    else:
        dest.mkdir()
        (dest / "..notes").write_text("mine\n", encoding="utf-8")
        (dest / "SKILL.md").symlink_to(source / "SKILL.md")

    _shell("cos_link_skill_dir", str(source), str(dest), str(install))

    assert not dest.is_symlink()
    assert (dest if dest_kind == "file" else dest / "..notes").read_text(
        encoding="utf-8"
    ) == "mine\n"


def test_the_shell_unlink_never_deletes_through_the_link(tmp_path: Path, install: Path) -> None:
    source = install / "core" / "skills" / "demo"
    dest = tmp_path / "skills" / "demo"
    dest.parent.mkdir()
    dest.symlink_to(source)

    _shell("cos_unlink_skill_dir", str(dest), str(install))

    assert not dest.is_symlink() and not dest.exists()
    assert (source / "SKILL.md").read_text(encoding="utf-8") == "source\n"


def test_no_installer_removes_a_path_inside_a_skill() -> None:
    """A disabled stack skill used to be `rm -f <skill>/SKILL.md`, through the link."""
    installer = (REPO / "src" / "core" / "scripts" / "install-adapter.sh").read_text(
        encoding="utf-8"
    )
    assert 'rm -f "${PROJECT_ROOT}/${SKILLS_REL}/${name}/' not in installer


@pytest.mark.parametrize("bad", ["../x", "a/b", "/abs", ".", ".provenance.json"])
def test_an_alias_with_an_unsafe_child_name_is_dropped(tmp_path: Path, bad: str) -> None:
    project = tmp_path / "project"
    (project / ".coding-os").mkdir(parents=True)
    alias = {
        "kind": "alias",
        "target": ".agents/skills/demo",
        "files": {bad: {"root": "core", "source": "core/skills/demo/SKILL.md"}},
    }
    manifest = {"version": 1, "entries": {".claude/skills/demo": alias}}
    (project / ".coding-os" / "managed-files.json").write_text(json.dumps(manifest))

    assert ".claude/skills/demo" not in localize_mod._load_manifest(project)


def test_a_meta_install_links_every_core_and_meta_skill_as_a_folder(tmp_path: Path) -> None:
    project = tmp_path / "meta"
    (project / ".coding-os").mkdir(parents=True)
    (project / ".coding-os" / "installed-manifest.json").write_text('{"templates": ["meta"]}')
    env = {**os.environ, "HOME": str(project)}
    install = REPO / "src" / "adapters" / "codex" / "install.sh"
    result = subprocess.run(
        ["bash", str(install)], cwd=project, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr

    expected = {p.parent.name for p in core_dir("skills").glob("*/SKILL.md")}
    expected |= {p.parent.name for p in templates_dir("meta", "skills").glob("*/SKILL.md")}
    skills = project / ".agents" / "skills"
    not_folder_links = sorted(n for n in expected if not (skills / n).is_symlink())
    assert not not_folder_links, f"not linked as a folder: {not_folder_links}"


@pytest.mark.skipif(
    shutil.which("codex") is None or not (REPO / ".agents" / "skills").is_dir(),
    reason="needs the codex CLI and this checkout's installed .agents/skills",
)
def test_codex_lists_every_skill_in_this_checkout() -> None:
    """The audit's C1 probe, run for real: `codex debug prompt-input` makes no model call."""
    out = subprocess.run(
        ["codex", "debug", "prompt-input", "--disable", "hooks", "-c", "mcp_servers={}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout
    expected = {p.parent.name for p in core_dir("skills").glob("*/SKILL.md")}
    missing = sorted(n for n in expected if f"/{n}/SKILL.md" not in out)
    assert not missing, f"codex does not list: {missing}"
