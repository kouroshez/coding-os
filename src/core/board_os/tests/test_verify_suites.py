"""Tests for core.board_os.verify_suites (Phase L.10 / TASK-100)."""

from __future__ import annotations

from pathlib import Path

import pytest

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
        ["core/hooks/enforce-verify.sh", "core/hooks/registry.yaml"], cfg,
    )
    assert "verify-hooks" in suites


def test_match_suites_resolves_board_os_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(
        ["core/board_os/transition_gates.py"], cfg,
    )
    assert "test-board_os" in suites


def test_match_suites_resolves_docs_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["docs/architecture.md"], cfg)
    assert "docs-lint" in suites


def test_match_suites_resolves_cli_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["cli/board_commands.py"], cfg)
    assert "test-cli" in suites


def test_match_suites_resolves_adapters_changes() -> None:
    cfg = load_verify_suites()
    suites = match_suites(["adapters/claude/install.sh"], cfg)
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
            "core/hooks/a.sh",
            "core/hooks/b.sh",
            "core/hooks/c.sh",
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
