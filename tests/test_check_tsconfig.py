"""Tests for the typescript check_tsconfig.py strictness auditor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src" / "core" / "skills" / "typescript" / "scripts"),
)

import check_tsconfig as ct  # noqa: E402

STRICT = {
    "strict": True,
    "noUncheckedIndexedAccess": True,
    "noImplicitOverride": True,
    "exactOptionalPropertyTypes": True,
    "noFallthroughCasesInSwitch": True,
}


def test_full_strict_is_clean() -> None:
    assert ct.audit({"compilerOptions": dict(STRICT)}) == []


def test_strict_off_flagged() -> None:
    opts = dict(STRICT, strict=False)
    findings = ct.audit({"compilerOptions": opts})
    assert any(f.startswith("strict !=") for f in findings)


def test_missing_recommended_flagged() -> None:
    findings = ct.audit({"compilerOptions": {"strict": True}})
    assert any("noUncheckedIndexedAccess" in f for f in findings)


def test_strip_jsonc_handles_comments_and_trailing_comma() -> None:
    text = '{\n  // line comment\n  "compilerOptions": {\n    "strict": true, /* blk */\n  },\n}'
    assert ct.load_tsconfig(text)["compilerOptions"]["strict"] is True


def test_extends_note_appended_when_findings() -> None:
    findings = ct.audit({"extends": "./base.json", "compilerOptions": {"strict": False}})
    assert any("extends" in f for f in findings)


def test_extends_no_note_when_clean() -> None:
    findings = ct.audit({"extends": "./base.json", "compilerOptions": dict(STRICT)})
    assert findings == []


def test_rejects_non_object_root() -> None:
    with pytest.raises(ValueError):
        ct.load_tsconfig("[1, 2, 3]")
