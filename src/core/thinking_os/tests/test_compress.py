"""Tests for compress.py prompt hardening + provenance (B2).

The Haiku summary feeds cos_search (narrative/concepts are matched), so the
prompt must preserve the observation Title's symbols verbatim and forbid
invention, and generated facts must carry a provenance marker. Verified
without an API call via the pure _build_prompt / _parse_json helpers.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compress import _build_prompt, _parse_json, _stamp_provenance


class TestBuildPrompt:
    def test_pins_title_symbols_verbatim(self) -> None:
        prompt = _build_prompt("Add compose_chain to formula_composer", "src/core/x.py")
        assert "VERBATIM" in prompt
        # the symbols the model must preserve are embedded for grounding
        assert "compose_chain" in prompt
        assert "formula_composer" in prompt

    def test_forbids_invention(self) -> None:
        prompt = _build_prompt("t", "f").lower()
        assert "do not invent" in prompt
        # the old hallucination-inviting instruction is gone
        assert "infer from file paths" not in prompt


class TestParseJson:
    def test_plain_json(self) -> None:
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_code_block_json(self) -> None:
        assert _parse_json('```json\n{"a": 2}\n```') == {"a": 2}

    def test_non_json_returns_none(self) -> None:
        assert _parse_json("sorry, no json here") is None


class TestStampProvenance:
    def test_stamps_generated_by_into_facts(self) -> None:
        out = _stamp_provenance({"facts": {"domain": "x"}}, "claude-haiku-4-5")
        assert out["facts"]["_generated_by"] == "claude-haiku-4-5"

    def test_noop_when_facts_missing_or_non_dict(self) -> None:
        assert _stamp_provenance({"narrative": "n"}, "m") == {"narrative": "n"}
        assert _stamp_provenance({"facts": []}, "m") == {"facts": []}

    def test_noop_on_none(self) -> None:
        assert _stamp_provenance(None, "m") is None
