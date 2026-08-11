"""`cos update` must expect the asset set install-adapter.sh actually links.

Fast unit tests on the enumerator — no scaffolding, so they stay out of the
slow lane that `test_cli_update.py` lives in.

The regression (TASK-876): install-adapter.sh skips AND unlinks every skill in
`.coding-os.yaml::disabled_skills`, but the enumerator listed all of them. The
diff therefore reported each disabled skill as missing and relinked it, silently
undoing `cos skill disable` on the next update.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cli._update_manifest import ADAPTERS_DIR, _build_target_assets, _disabled_skills
from cli.update import _sync_hook_registration


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


# ---------------------------------------------------------------------------
# Hook re-registration: linking a hook script is only half an install — the
# runtime fires what the settings file registers, so a settings file that fell
# behind the template leaves newly shipped hooks symlinked but never running.
# ---------------------------------------------------------------------------


def _settings(project: Path, hooks: dict, **extra) -> Path:
    path = project / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks, **extra}, indent=2), encoding="utf-8")
    return path


def _template_hooks() -> dict:
    raw = (ADAPTERS_DIR / "claude" / "settings.template.json").read_text(encoding="utf-8")
    return json.loads(raw.replace("{{HOOKS_DIR}}", ".claude/hooks")).get("hooks") or {}


def test_up_to_date_registration_reports_no_change(tmp_path: Path) -> None:
    _settings(tmp_path, _template_hooks())

    assert _sync_hook_registration(tmp_path, "claude", dry_run=False) is False


def test_stale_registration_is_restored(tmp_path: Path) -> None:
    path = _settings(tmp_path, {})

    assert _sync_hook_registration(tmp_path, "claude", dry_run=False) is True
    assert json.loads(path.read_text(encoding="utf-8"))["hooks"] == _template_hooks()


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    path = _settings(tmp_path, {})

    assert _sync_hook_registration(tmp_path, "claude", dry_run=True) is True
    assert json.loads(path.read_text(encoding="utf-8"))["hooks"] == {}


def test_user_owned_keys_survive_re_registration(tmp_path: Path) -> None:
    path = _settings(tmp_path, {}, permissions={"allow": ["Bash(ls:*)"]}, model="opus")

    _sync_hook_registration(tmp_path, "claude", dry_run=False)

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["permissions"] == {"allow": ["Bash(ls:*)"]}
    assert written["model"] == "opus"


def test_missing_settings_file_is_not_an_error(tmp_path: Path) -> None:
    assert _sync_hook_registration(tmp_path, "claude", dry_run=False) is False
