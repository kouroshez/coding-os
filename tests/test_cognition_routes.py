"""Chat priming from the onboarding intake, the cognition chat route's prompt seed."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src" / "core") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src" / "core"))


# ---------------------------------------------------------------------------
# Chat priming from the onboarding intake — TASK-364
# ---------------------------------------------------------------------------


class TestChatPriming:
    def _module(self):
        import importlib

        return importlib.import_module("core.web.routes.cognition")

    def test_intake_appended_to_system_prompt(self, tmp_path):
        cog = self._module()
        meta = tmp_path / "docs" / "_meta"
        meta.mkdir(parents=True)
        (meta / "project-description.md").write_text(
            "# Project Description (onboarding intake)\n\nInvoice automation for agencies.\n",
            encoding="utf-8",
        )
        base = {"type": "preset", "preset": "claude_code", "append": "BASE"}
        primed = cog._prime_with_project_description(base, str(tmp_path))
        assert primed["append"].startswith("BASE")
        assert "Project context (onboarding intake)" in primed["append"]
        assert "Invoice automation for agencies." in primed["append"]
        assert base["append"] == "BASE"  # input not mutated

    def test_missing_intake_leaves_prompt_untouched(self, tmp_path):
        cog = self._module()
        base = {"type": "preset", "preset": "claude_code", "append": "BASE"}
        assert cog._prime_with_project_description(base, str(tmp_path)) is base

    def test_intake_is_bounded(self, tmp_path):
        cog = self._module()
        meta = tmp_path / "docs" / "_meta"
        meta.mkdir(parents=True)
        (meta / "project-description.md").write_text("x" * 10_000, encoding="utf-8")
        primed = cog._prime_with_project_description(
            {"type": "preset", "preset": "claude_code", "append": "BASE"}, str(tmp_path)
        )
        assert len(primed["append"]) < 2_200  # 2000-char intake cap + framing
