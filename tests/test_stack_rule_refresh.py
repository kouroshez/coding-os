"""A stack-rule correction must reach installed projects without eating user edits.

Core rules are symlinks and propagate the moment they change. Stack rules are
copies, so `cos update` saw nothing to do and a corrected template reached no
existing install at all. The baseline that separates "user edited it" from
"template moved on" is the byte-exact mirror `cos init` already writes under
`.coding-os/src/templates/<stack>/rules/` — no hash sidecar required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli._init_scaffold import refresh_stack_rules

STACK = "wordpress"
RULE = "backend.md"
AGENT = "claude"
REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "src" / "templates" / STACK / "rules" / RULE


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """A project whose installed rule and mirror both match the template."""
    if not TEMPLATE.is_file():
        pytest.skip(f"no template at {TEMPLATE}")
    body = TEMPLATE.read_text(encoding="utf-8")

    template_root = tmp_path / "templates" / STACK / "rules"
    template_root.mkdir(parents=True)
    (template_root / RULE).write_text(body, encoding="utf-8")

    rules_dir = tmp_path / "project" / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    installed_rule = rules_dir / f"{STACK}-{RULE}"
    installed_rule.write_text(body, encoding="utf-8")

    mirror_dir = tmp_path / "project" / ".coding-os" / "src" / "templates" / STACK / "rules"
    mirror_dir.mkdir(parents=True)
    mirror = mirror_dir / RULE
    mirror.write_text(body, encoding="utf-8")

    class _Stack:
        source_dir = template_root.parent

    class _Adapter:
        supports_rules = True
        rules_dir = ".claude/rules"

    monkeypatch.setattr("cli._init_scaffold._get_stack_registry", lambda: {STACK: _Stack()})
    monkeypatch.setattr("cli._init_scaffold._get_adapter_registry", lambda: {AGENT: _Adapter()})

    return {
        "project": tmp_path / "project",
        "template": template_root / RULE,
        "installed": installed_rule,
        "mirror": mirror,
    }


def test_untouched_rule_is_refreshed(installed: dict[str, Path]) -> None:
    installed["template"].write_text("corrected template\n", encoding="utf-8")

    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert refreshed == [f"{STACK}-{RULE}"]
    assert kept == []
    assert installed["installed"].read_text(encoding="utf-8") == "corrected template\n"


def test_mirror_advances_with_the_rule(installed: dict[str, Path]) -> None:
    """A stale mirror would make the next refresh read the file as user-edited."""
    installed["template"].write_text("corrected template\n", encoding="utf-8")

    refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert installed["mirror"].read_text(encoding="utf-8") == "corrected template\n"


def test_user_edited_rule_is_kept(installed: dict[str, Path]) -> None:
    installed["installed"].write_text("my own version\n", encoding="utf-8")
    installed["template"].write_text("corrected template\n", encoding="utf-8")

    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert refreshed == []
    assert kept == [f"{STACK}-{RULE}"]
    assert installed["installed"].read_text(encoding="utf-8") == "my own version\n"


def test_dry_run_writes_nothing(installed: dict[str, Path]) -> None:
    installed["template"].write_text("corrected template\n", encoding="utf-8")
    before = installed["installed"].read_text(encoding="utf-8")

    refreshed, _ = refresh_stack_rules(STACK, installed["project"], [AGENT], dry_run=True)

    assert refreshed == [f"{STACK}-{RULE}"], "dry run still reports what it would do"
    assert installed["installed"].read_text(encoding="utf-8") == before


def test_missing_mirror_says_so_instead_of_accusing_the_user(installed: dict[str, Path]) -> None:
    """Without a baseline there is no evidence either way — decline to write, and
    say the baseline is missing rather than assert an edit that may not exist."""
    installed["mirror"].unlink()
    installed["template"].write_text("corrected template\n", encoding="utf-8")

    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert refreshed == []
    assert kept == [f"{STACK}-{RULE} (no baseline to compare against)"]
    assert installed["installed"].read_text(encoding="utf-8") != "corrected template\n"


def test_every_adapter_is_decided_against_the_same_mirror(
    installed: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Advancing the mirror per adapter refreshed the first and froze the rest."""

    class _Codex:
        supports_rules = True
        rules_dir = ".codex/rules"

    class _Claude:
        supports_rules = True
        rules_dir = ".claude/rules"

    monkeypatch.setattr(
        "cli._init_scaffold._get_adapter_registry",
        lambda: {AGENT: _Claude(), "codex": _Codex()},
    )
    codex_rule = installed["project"] / ".codex" / "rules" / f"{STACK}-{RULE}"
    codex_rule.parent.mkdir(parents=True)
    codex_rule.write_text(installed["installed"].read_text(encoding="utf-8"), encoding="utf-8")
    installed["template"].write_text("corrected template\n", encoding="utf-8")

    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT, "codex"])

    assert kept == [], "no adapter may be reported as edited by another adapter's refresh"
    assert len(refreshed) == 2
    assert codex_rule.read_text(encoding="utf-8") == "corrected template\n"
    assert installed["installed"].read_text(encoding="utf-8") == "corrected template\n"


def test_unchanged_template_is_a_no_op(installed: dict[str, Path]) -> None:
    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert (refreshed, kept) == ([], [])


def test_stale_mirror_does_not_accuse_an_untouched_rule(installed: dict[str, Path]) -> None:
    """Installs predating the mirror being kept in step are common — this repo's
    own mirror is months behind. A rule already equal to its template needs no
    refresh and is nobody's edit, so it must produce no line at all."""
    installed["mirror"].write_text("what the template said months ago\n", encoding="utf-8")

    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert (refreshed, kept) == ([], [])


def test_uninstalled_rule_is_never_created(installed: dict[str, Path]) -> None:
    """Refresh updates what a project has; it does not hand it new rules."""
    installed["installed"].unlink()
    installed["template"].write_text("corrected template\n", encoding="utf-8")

    refreshed, kept = refresh_stack_rules(STACK, installed["project"], [AGENT])

    assert (refreshed, kept) == ([], [])
    assert not installed["installed"].exists()


def test_no_agent_is_a_no_op(installed: dict[str, Path]) -> None:
    assert refresh_stack_rules(STACK, installed["project"], [None]) == ([], [])
