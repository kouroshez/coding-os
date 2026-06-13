"""Criterion 4 guard (TASK-366): the shared/{contracts,<lang>}/ convention is
documented in the clean-code + backend-fundamentals skills."""

from __future__ import annotations

from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "src" / "core" / "skills"


def test_clean_code_documents_shared_convention() -> None:
    text = (SKILLS / "clean-code" / "SKILL.md").read_text(encoding="utf-8")
    assert "Cross-Service Code Placement" in text
    assert "src/shared/<lang>/" in text
    assert "src/shared/contracts/" in text
    assert "reuse-first" in text.lower()


def test_backend_fundamentals_references_shared_convention() -> None:
    text = (SKILLS / "backend-fundamentals" / "SKILL.md").read_text(encoding="utf-8")
    assert "src/shared/contracts/" in text
    assert "src/shared/<lang>/" in text
