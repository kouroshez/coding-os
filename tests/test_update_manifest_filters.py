"""`cos update` must expect the asset set install-adapter.sh actually links.

Fast unit tests on the enumerator — no scaffolding, so they stay out of the
slow lane that `test_cli_update.py` lives in.

The regression (TASK-876): install-adapter.sh skips AND unlinks every skill in
`.coding-os.yaml::disabled_skills`, but the enumerator listed all of them. The
diff therefore reported each disabled skill as missing and relinked it, silently
undoing `cos skill disable` on the next update.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cli._update_manifest import _build_target_assets, _disabled_skills


def _project(tmp_path: Path, config: dict) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".coding-os.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return tmp_path


def test_no_project_means_no_opt_outs() -> None:
    assert _disabled_skills(None) == frozenset()


def test_reads_the_disabled_skills_key(tmp_path: Path) -> None:
    project = _project(tmp_path, {"disabled_skills": ["a11y", "observability"]})

    assert _disabled_skills(project) == frozenset({"a11y", "observability"})


def test_absent_key_disables_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path, {"agents": ["claude"]})

    assert _disabled_skills(project) == frozenset()


def test_disabled_skill_is_not_an_expected_asset(tmp_path: Path) -> None:
    enabled = _build_target_assets("claude", [], _project(tmp_path / "on", {}))
    names = {asset.name for asset in enabled["skills"]}
    assert "a11y" in names, "fixture assumption: a11y ships as a core skill"

    disabled = _build_target_assets(
        "claude", [], _project(tmp_path / "off", {"disabled_skills": ["a11y"]})
    )

    assert "a11y" not in {asset.name for asset in disabled["skills"]}
    assert {asset.name for asset in disabled["skills"]} == names - {"a11y"}


def test_opting_out_leaves_the_other_asset_kinds_alone(tmp_path: Path) -> None:
    enabled = _build_target_assets("claude", [], _project(tmp_path / "on", {}))
    disabled = _build_target_assets(
        "claude", [], _project(tmp_path / "off", {"disabled_skills": ["a11y"]})
    )

    for kind in ("hooks", "rules", "commands"):
        assert {a.name for a in enabled[kind]} == {a.name for a in disabled[kind]}
