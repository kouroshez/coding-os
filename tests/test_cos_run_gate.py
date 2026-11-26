"""`cos run` applies the test governor itself and writes the verify ledger.

Spec: docs/engineering/test-governance.md § cos run.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import yaml
from click.testing import CliRunner

from board_os import verify_suites_cli
from cli import _run_gate
from cli.main import cli

REPO = Path(__file__).resolve().parent.parent


def _suite_project(tmp_path: Path, monkeypatch, shell: str) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os.yaml").write_text(yaml.dump({"commands": {"test-backend": shell}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / ".coding-os"))
    for name in ("COS_TEST_FORCE", "COS_PANEL_ID", "COS_FULL_SWEEP_OK"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / ".coding-os"


def test_cos_run_ledgers_a_failing_suite_itself(tmp_path: Path, monkeypatch) -> None:
    state = _suite_project(tmp_path, monkeypatch, "exit 4")
    assert CliRunner().invoke(cli, ["run", "test-backend"]).exit_code == 4
    ledger = json.loads((state / ".last-verify.json").read_text())
    assert ledger["test-backend"]["status"] == "FAIL"
    assert not (state / ".test-run.lock").exists()


def test_cos_run_refuses_a_suite_already_green_unless_forced(tmp_path: Path, monkeypatch) -> None:
    state = _suite_project(tmp_path, monkeypatch, "echo ran > marker.txt")
    (state / ".last-verify.json").write_text(
        json.dumps({"test-backend": {"status": "PASS", "ts": int(time.time())}})
    )
    result = CliRunner().invoke(cli, ["run", "test-backend"])
    assert result.exit_code == 2 and "already green" in result.output
    assert not (tmp_path / "marker.txt").exists()
    monkeypatch.setenv("COS_TEST_FORCE", "1")
    assert CliRunner().invoke(cli, ["run", "test-backend"]).exit_code == 0
    assert (tmp_path / "marker.txt").exists()


def test_cos_run_dedup_is_keyed_to_the_git_tree(tmp_path: Path, monkeypatch) -> None:
    state = _suite_project(tmp_path, monkeypatch, "echo ran >> marker.txt")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True
        )
    entry = {"status": "PASS", "ts": int(time.time()), **verify_suites_cli._tree_state(tmp_path)}
    (state / ".last-verify.json").write_text(json.dumps({"test-backend": entry}))
    assert CliRunner().invoke(cli, ["run", "test-backend"]).exit_code == 2
    (tmp_path / "app.py").write_text("changed = True\n")
    assert CliRunner().invoke(cli, ["run", "test-backend"]).exit_code == 0


def test_cos_run_gate_constants_match_the_test_governor() -> None:
    governor = (REPO / "src" / "core" / "hooks" / "test-governor.sh").read_text()
    assert f"LOCK_TTL={_run_gate._LOCK_TTL_SECONDS}\n" in governor
    assert f'"${{#REASON}}" -ge {_run_gate._MIN_OVERRIDE_REASON_CHARS} ' in governor


def test_cos_run_refuses_a_full_pytest_sweep_without_an_override(
    tmp_path: Path, monkeypatch
) -> None:
    _suite_project(tmp_path, monkeypatch, "echo ran > marker.txt")
    (tmp_path / ".coding-os.yaml").write_text(
        yaml.dump({"commands": {"test-all": "pytest -q && echo ran > marker.txt"}})
    )
    result = CliRunner().invoke(cli, ["run", "test-all"])
    assert result.exit_code == 2 and "full pytest sweep" in result.output
    assert not (tmp_path / "marker.txt").exists()


def test_cos_run_waits_for_a_live_heavy_run(tmp_path: Path, monkeypatch) -> None:
    state = _suite_project(tmp_path, monkeypatch, "echo ran > marker.txt")
    lock = {
        "suite": "test-x",
        "agent": "codex",
        "agent_pid": os.getpid(),
        "started_ts": int(time.time()),
    }
    (state / ".test-run.lock").write_text(json.dumps(lock))
    result = CliRunner().invoke(cli, ["run", "test-backend"])
    assert result.exit_code == 2 and "codex is running test-x" in result.output
    assert not (tmp_path / "marker.txt").exists()
    assert json.loads((state / ".test-run.lock").read_text()) == lock


def test_cos_run_replaces_a_lock_whose_owner_is_gone(tmp_path: Path, monkeypatch) -> None:
    state = _suite_project(tmp_path, monkeypatch, "echo ran > marker.txt")
    gone = subprocess.Popen(["true"])
    gone.wait()
    lock = {"suite": "test-x", "agent_pid": gone.pid, "started_ts": int(time.time())}
    (state / ".test-run.lock").write_text(json.dumps(lock))
    assert CliRunner().invoke(cli, ["run", "test-backend"]).exit_code == 0
    assert (tmp_path / "marker.txt").exists()
    assert not (state / ".test-run.lock").exists()
