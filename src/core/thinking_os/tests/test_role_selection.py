"""Tests for TASK-057 role selection + active-role phase switch.

Covers the three units the post-merge review flagged as untested:

  - formula_composer.signals_from_prompt — prompt → rich TaskSignals so the
    composed chain VARIES per task (regression guard against the old
    every-task-→-['analyst'] bug).
  - roles_state.stamp_roles / advance_role — chain persistence + phase-driven
    active-role advance, including the "never invent a role not in the chain"
    invariant.
  - advance_role._phase_for — tool/file → work phase mapping (edit/verify/doc).

These run with bare imports (conftest puts core/thinking_os + its parent on
sys.path). File-writing units use tmp_path so no real state dir is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import formula_composer as fc
import roles_state

# advance_role helper lives under hooks/_helpers — add it to the path once.
_HELPERS_DIR = Path(__file__).resolve().parents[3] / "core" / "hooks" / "_helpers"
if str(_HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPERS_DIR))
import advance_role  # noqa: E402  (path set up above)


# ---------------------------------------------------------------------------
# formula_composer.signals_from_prompt — the core bug fix
# ---------------------------------------------------------------------------
class TestSignalsFromPrompt:
    @pytest.mark.parametrize(
        "prompt,expected_action",
        [
            ("debug the failing auth integration test", "debug"),
            ("audit all security and auth code for vulnerabilities", "audit"),
            ("review the open PR diff", "review"),
            ("research the best way to optimize graph traversal", "research"),
            ("refactor the database migration module", "refactor"),
            ("write documentation for the new API", "document"),
            ("deploy the release to production", "deploy"),
            ("add a new MCP tool endpoint", "create"),
            ("fix the off-by-one in the parser", "modify"),
        ],
    )
    def test_action_extracted_from_prompt(self, prompt: str, expected_action: str) -> None:
        sig = fc.signals_from_prompt(prompt, "COMPLICATED", 2)
        assert sig.action == expected_action

    def test_debug_action_takes_precedence_over_generic_modify(self) -> None:
        # "fix" alone is modify, but "failing"/"debug" must win → debugger.
        sig = fc.signals_from_prompt("fix the failing test", "COMPLICATED", 1)
        assert sig.action == "debug"

    def test_domain_extracted(self) -> None:
        sig = fc.signals_from_prompt("add an auth endpoint to the backend api", "COMPLICATED", 2)
        assert "security" in sig.domain
        assert "backend" in sig.domain

    def test_unknown_action_when_no_keyword(self) -> None:
        sig = fc.signals_from_prompt("the quick brown fox", "COMPLICATED", 1)
        assert sig.action == "unknown"

    def test_scope_size_large_on_breadth_keyword(self) -> None:
        assert fc.signals_from_prompt("fix all the tests", "COMPLICATED", 1).scope_size == "large"

    def test_scope_size_small_on_short_prompt(self) -> None:
        assert fc.signals_from_prompt("add helper", "COMPLICATED", 1).scope_size == "small"

    def test_scope_size_medium_on_normal_prompt(self) -> None:
        # 12+ words, no breadth keyword, well under 200 → medium.
        prompt = (
            "update the user serializer so it includes the new email field "
            "and keeps the existing phone number column working as before"
        )
        assert fc.signals_from_prompt(prompt, "COMPLICATED", 2).scope_size == "medium"

    def test_invalid_complexity_defaults_to_complicated(self) -> None:
        sig = fc.signals_from_prompt("do something", "NONSENSE", 1)
        assert sig.complexity == "COMPLICATED"

    def test_empty_prompt_is_safe(self) -> None:
        sig = fc.signals_from_prompt("", "COMPLEX", 3)
        assert sig.action == "unknown"
        assert sig.domain == []


class TestChainVariesPerTask:
    """The regression guard: different prompts → different chains, NOT all analyst."""

    def _chain(self, prompt: str, complexity: str = "COMPLICATED", dims: int = 2) -> list[str]:
        sig = fc.signals_from_prompt(prompt, complexity, dims)
        return fc.compose_chain(signals=sig).chain

    def test_debug_prompt_leads_with_debugger(self) -> None:
        assert self._chain("debug the failing auth test")[0] == "debugger"

    def test_audit_prompt_selects_security_auditor(self) -> None:
        assert "security_auditor" in self._chain("audit all security code for vulnerabilities")

    def test_refactor_prompt_leads_with_refactorer(self) -> None:
        assert self._chain("refactor the migration module")[0] == "refactorer"

    def test_research_prompt_selects_researcher(self) -> None:
        assert "researcher" in self._chain("research the best way to optimize traversal", "COMPLEX", 3)

    def test_distinct_prompts_yield_distinct_chains(self) -> None:
        # The whole point of TASK-057: not every task collapses to ['analyst'].
        chains = {
            tuple(self._chain(p))
            for p in (
                "debug the failing test",
                "audit security code",
                "refactor the module",
                "write documentation",
            )
        }
        assert len(chains) >= 3  # at least 3 of the 4 are distinct


# ---------------------------------------------------------------------------
# roles_state — stamp + advance
# ---------------------------------------------------------------------------
class TestStampRoles:
    def test_writes_chain_and_lead(self, tmp_path: Path) -> None:
        roles_state.stamp_roles(["analyst", "implementer", "reviewer"], str(tmp_path))
        assert json.loads((tmp_path / ".roles").read_text()) == [
            "analyst",
            "implementer",
            "reviewer",
        ]
        assert (tmp_path / ".role").read_text() == "analyst"

    def test_empty_chain_writes_no_lead(self, tmp_path: Path) -> None:
        roles_state.stamp_roles([], str(tmp_path))
        assert json.loads((tmp_path / ".roles").read_text()) == []
        assert not (tmp_path / ".role").exists()

    def test_never_raises_on_unwritable_dir(self, tmp_path: Path) -> None:
        bad = tmp_path / "afile"
        bad.write_text("x")  # a file, not a dir → mkdir under it fails
        # Must NOT raise (fire-and-forget contract).
        roles_state.stamp_roles(["analyst"], str(bad / "sub"))


class TestAdvanceRole:
    def _seed(self, tmp_path: Path, chain: list[str]) -> None:
        (tmp_path / ".roles").write_text(json.dumps(chain))

    def test_advances_to_in_chain_candidate(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["debugger", "reviewer", "documenter"])
        chosen = roles_state.advance_role("verify", str(tmp_path))
        assert chosen == "reviewer"
        assert (tmp_path / ".role").read_text() == "reviewer"

    def test_edit_phase_picks_first_available_builder(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["analyst", "refactorer", "reviewer"])  # no implementer
        assert roles_state.advance_role("edit", str(tmp_path)) == "refactorer"

    def test_never_invents_role_not_in_chain(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["implementer"])  # reviewer NOT present
        chosen = roles_state.advance_role("verify", str(tmp_path))
        assert chosen is None
        assert not (tmp_path / ".role").exists()  # .role untouched

    def test_missing_roles_file_is_noop(self, tmp_path: Path) -> None:
        assert roles_state.advance_role("edit", str(tmp_path)) is None

    def test_empty_chain_is_noop(self, tmp_path: Path) -> None:
        self._seed(tmp_path, [])
        assert roles_state.advance_role("edit", str(tmp_path)) is None

    def test_unknown_phase_is_noop(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["analyst", "implementer"])
        assert roles_state.advance_role("nonsense", str(tmp_path)) is None

    def test_corrupt_roles_file_is_noop(self, tmp_path: Path) -> None:
        (tmp_path / ".roles").write_text("{not json")
        assert roles_state.advance_role("edit", str(tmp_path)) is None


# ---------------------------------------------------------------------------
# advance_role._phase_for — tool/file → phase
# ---------------------------------------------------------------------------
class TestPhaseFor:
    def test_code_write_is_edit(self) -> None:
        assert advance_role._phase_for("Write", "", "src/core/foo.py") == "edit"

    def test_markdown_write_is_doc(self) -> None:
        assert advance_role._phase_for("Write", "", "docs/spec.md") == "doc"

    def test_docs_path_is_doc(self) -> None:
        assert advance_role._phase_for("Edit", "", "src/docs/anything.py") == "doc"

    def test_verify_command_is_verify(self) -> None:
        assert advance_role._phase_for("Bash", "uv run pytest foo", "") == "verify"
        assert advance_role._phase_for("Bash", "make verify", "") == "verify"

    def test_non_verify_bash_is_none(self) -> None:
        assert advance_role._phase_for("Bash", "ls -la", "") is None

    def test_unrelated_tool_is_none(self) -> None:
        assert advance_role._phase_for("Read", "", "foo.py") is None


class TestAdvanceRoleMain:
    """End-to-end glue: argv → phase → advance_role → .role on disk."""

    def _seed(self, tmp_path: Path, chain: list[str]) -> None:
        (tmp_path / ".roles").write_text(json.dumps(chain))

    def test_main_write_advances_to_implementer(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["analyst", "implementer", "reviewer"])
        rc = advance_role.main(["advance_role.py", "Write", str(tmp_path), "", "src/foo.py"])
        assert rc == 0
        assert (tmp_path / ".role").read_text() == "implementer"

    def test_main_verify_bash_advances_to_reviewer(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["debugger", "reviewer"])
        rc = advance_role.main(["advance_role.py", "Bash", str(tmp_path), "uv run pytest"])
        assert rc == 0
        assert (tmp_path / ".role").read_text() == "reviewer"

    def test_main_too_few_args_is_noop(self, tmp_path: Path) -> None:
        assert advance_role.main(["advance_role.py", "Write"]) == 0

    def test_main_unrelated_tool_is_noop(self, tmp_path: Path) -> None:
        self._seed(tmp_path, ["analyst", "implementer"])
        rc = advance_role.main(["advance_role.py", "Read", str(tmp_path), "", "foo.py"])
        assert rc == 0
        assert not (tmp_path / ".role").exists()
