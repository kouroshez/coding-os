"""Tests for core.board_os.verify_suites (TASK-100)."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from core.board_os import verify_suites_cli
from core.board_os.verify_suites import (
    SuiteRule,
    VerifySuitesConfig,
    VerifySuitesError,
    get_suite_command,
    load_verify_suites,
    match_suites,
)


def test_default_yaml_loads_cleanly() -> None:
    cfg = load_verify_suites()
    assert "verify-hooks" in cfg.suites
    assert "test-board_os" in cfg.suites
    assert "docs-lint" in cfg.suites


def test_match_suites_resolves_core_hooks_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(
        ["src/core/hooks/enforce-verify.sh", "src/core/hooks/registry.yaml"],
        cfg,
    )
    assert "verify-hooks" in suites


def test_match_suites_resolves_board_os_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(
        ["src/core/board_os/transition_gates.py"],
        cfg,
    )
    assert "test-board_os" in suites


def test_match_suites_resolves_docs_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["docs/architecture.md"], cfg)
    assert "docs-lint" in suites


def test_match_suites_resolves_cli_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["src/cli/board_commands.py"], cfg)
    assert "test-cli" in suites


def test_match_suites_resolves_adapters_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["src/adapters/claude/install.sh"], cfg)
    assert "test-adapters" in suites


def test_match_suites_handles_unrelated_paths() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["random/unrelated/file.txt"], cfg)
    assert suites == []


def test_match_suites_handles_empty_input() -> None:
    cfg = load_verify_suites()
    assert match_suites([], cfg) == []


def test_match_suites_returns_each_suite_at_most_once() -> None:
    cfg = load_verify_suites()
    suites = match_suites(
        [
            "src/core/hooks/a.sh",
            "src/core/hooks/b.sh",
            "src/core/hooks/c.sh",
        ],
        cfg,
    )
    assert suites.count("verify-hooks") == 1


def test_match_suites_resolves_recursive_glob() -> None:
    cfg = VerifySuitesConfig(
        suites={
            "templates-test": SuiteRule(
                paths=["src/templates/**/scaffold/**"],
                command="echo run",
            ),
        },
    )
    suites = match_suites(
        ["src/templates/django/scaffold/x.py", "src/templates/nextjs/scaffold/sub/y.tsx"],
        cfg,
    )
    assert suites == ["templates-test"]


def test_consumer_override_replaces_meta_suite(tmp_path: Path) -> None:
    """A consumer .coding-os/verify-suites.yaml replaces a meta suite."""
    consumer_dir = tmp_path / ".coding-os"
    consumer_dir.mkdir()
    (consumer_dir / "verify-suites.yaml").write_text(
        """
        version: 1
        suites:
          test-backend:
            paths: ["src/**/*.py"]
            command: "pytest src/"
        """,
        encoding="utf-8",
    )
    cfg = load_verify_suites(project_root=tmp_path)
    rule = cfg.suites["test-backend"]
    assert rule.paths == ["src/**/*.py"]
    assert rule.command == "pytest src/"


def test_get_suite_command_resolves() -> None:
    cfg = load_verify_suites()
    cmd = get_suite_command("verify-hooks", cfg)
    assert cmd is not None
    assert "make verify-hooks" in cmd


def test_get_suite_command_unknown_returns_none() -> None:
    cfg = load_verify_suites()
    assert get_suite_command("not-a-real-suite", cfg) is None


def test_malformed_yaml_raises_structured_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("::not: valid: yaml: ::", encoding="utf-8")
    with pytest.raises(VerifySuitesError):
        load_verify_suites(meta_path=bad)


def test_no_path_globs_means_never_matches() -> None:
    """A suite with empty paths list must not auto-match every change."""
    cfg = VerifySuitesConfig(
        suites={
            "explicit-only": SuiteRule(paths=[], command="echo run"),
            "always-match": SuiteRule(paths=["**/*"], command="echo all"),
        },
    )
    suites = match_suites(["any/file.py"], cfg)
    assert "explicit-only" not in suites
    assert "always-match" in suites


# ── Commit-keyed freshness (TASK-328) ────────────────────────────────


def _ledger(tmp_path: Path, entry: dict) -> Path:
    vf = tmp_path / ".last-verify.json"
    vf.write_text(json.dumps({"test-board_os": entry}), encoding="utf-8")
    return vf


def _fresh_entry(**overrides) -> dict:
    entry = {
        "status": "PASS",
        "ts": int(time.time()),
        "git_head": "a" * 40,
        "dirty_digest": "clean",
    }
    entry.update(overrides)
    return entry


class TestCommitKeyedFreshness:
    def _patch_tree(self, monkeypatch: pytest.MonkeyPatch, head: str, digest: str) -> None:
        monkeypatch.setattr(
            verify_suites_cli,
            "_tree_state",
            lambda repo_root=None: {"git_head": head, "dirty_digest": digest},
        )

    def test_pass_on_same_tree_is_fresh(self, tmp_path: Path, monkeypatch) -> None:
        self._patch_tree(monkeypatch, "a" * 40, "clean")
        missing, ok = verify_suites_cli._check_suites(
            ["test-board_os"], _ledger(tmp_path, _fresh_entry())
        )
        assert ok == ["test-board_os"]
        assert missing == []

    def test_new_commit_invalidates_pass(self, tmp_path: Path, monkeypatch) -> None:
        self._patch_tree(monkeypatch, "b" * 40, "clean")
        missing, _ok = verify_suites_cli._check_suites(
            ["test-board_os"], _ledger(tmp_path, _fresh_entry())
        )
        assert missing == ["test-board_os"]

    def test_dirty_diff_change_invalidates_pass(self, tmp_path: Path, monkeypatch) -> None:
        self._patch_tree(monkeypatch, "a" * 40, "deadbeef")
        missing, _ok = verify_suites_cli._check_suites(
            ["test-board_os"], _ledger(tmp_path, _fresh_entry())
        )
        assert missing == ["test-board_os"]

    def test_v1_entry_without_keys_is_stale(self, tmp_path: Path, monkeypatch) -> None:
        self._patch_tree(monkeypatch, "a" * 40, "clean")
        entry = {"status": "PASS", "ts": int(time.time())}
        missing, _ok = verify_suites_cli._check_suites(
            ["test-board_os"], _ledger(tmp_path, entry)
        )
        assert missing == ["test-board_os"]

    def test_expired_ts_stale_even_on_same_tree(self, tmp_path: Path, monkeypatch) -> None:
        self._patch_tree(monkeypatch, "a" * 40, "clean")
        entry = _fresh_entry(ts=int(time.time()) - 100_000)
        missing, _ok = verify_suites_cli._check_suites(
            ["test-board_os"], _ledger(tmp_path, entry)
        )
        assert missing == ["test-board_os"]

    def test_no_git_degrades_to_time_only(self, tmp_path: Path, monkeypatch) -> None:
        self._patch_tree(monkeypatch, "", "")
        entry = {"status": "PASS", "ts": int(time.time())}
        missing, ok = verify_suites_cli._check_suites(
            ["test-board_os"], _ledger(tmp_path, entry)
        )
        assert ok == ["test-board_os"]
        assert missing == []


class TestTreeState:
    @staticmethod
    def _git(cwd: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        self._git(tmp_path, "init", "-q")
        self._git(tmp_path, "config", "user.email", "t@t")
        self._git(tmp_path, "config", "user.name", "t")
        (tmp_path / "f.txt").write_text("v1", encoding="utf-8")
        self._git(tmp_path, "add", "f.txt")
        self._git(tmp_path, "commit", "-qm", "c1")
        return tmp_path

    def test_clean_tree_digest_is_clean(self, repo: Path) -> None:
        state = verify_suites_cli._tree_state(repo)
        assert len(state["git_head"]) == 40
        assert state["dirty_digest"] == "clean"

    def test_tracked_edit_changes_digest_not_head(self, repo: Path) -> None:
        before = verify_suites_cli._tree_state(repo)
        (repo / "f.txt").write_text("v2", encoding="utf-8")
        after = verify_suites_cli._tree_state(repo)
        assert after["git_head"] == before["git_head"]
        assert after["dirty_digest"] != before["dirty_digest"]
        assert after["dirty_digest"] != "clean"

    def test_new_commit_changes_head_and_resets_digest(self, repo: Path) -> None:
        (repo / "f.txt").write_text("v2", encoding="utf-8")
        before = verify_suites_cli._tree_state(repo)
        self._git(repo, "add", "f.txt")
        self._git(repo, "commit", "-qm", "c2")
        after = verify_suites_cli._tree_state(repo)
        assert after["git_head"] != before["git_head"]
        assert after["dirty_digest"] == "clean"

    def test_task_worklog_churn_is_excluded(self, repo: Path) -> None:
        before = verify_suites_cli._tree_state(repo)
        tasks_dir = repo / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-001-x.md").write_text("- log line", encoding="utf-8")
        after = verify_suites_cli._tree_state(repo)
        assert after == before

    def test_non_repo_returns_empty(self, tmp_path: Path) -> None:
        state = verify_suites_cli._tree_state(tmp_path / "nowhere")
        assert state == {"git_head": "", "dirty_digest": ""}

    def test_tree_state_subcommand_prints_json(self, repo: Path, capsys, monkeypatch) -> None:
        monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))
        assert verify_suites_cli.main(["tree-state"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert set(payload) == {"git_head", "dirty_digest"}
