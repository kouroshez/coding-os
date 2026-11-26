"""SSOT for the golden snapshot matrix: (section_id, agent, [stacks]).

Imported by src/scripts/capture_golden.py (the writer) and
tests/test_golden_parity.py (the asserter) so the captured set and the
asserted set can never drift — a fixture captured but not asserted (or
vice versa) would be drift-blind CI.
"""

from __future__ import annotations

SECTIONS: list[tuple[str, str, list[str]]] = [
    ("claude_base", "claude", []),
    ("claude_django", "claude", ["django"]),
    ("claude_nextjs", "claude", ["nextjs"]),
    ("claude_node-express", "claude", ["node-express"]),
    ("claude_vue-nuxt", "claude", ["vue-nuxt"]),
    ("codex_base", "codex", []),
    ("codex_django", "codex", ["django"]),
    ("codex_nextjs", "codex", ["nextjs"]),
]

# Claude Code discovers nested .claude/ dirs, so a captured one would load every
# golden copy of the skills and rules into this repo's own sessions.
_LIVE_CLAUDE, _STORED_CLAUDE = ".claude/", "dot-claude/"


def stored_rel(rel: str) -> str:
    return _STORED_CLAUDE + rel[len(_LIVE_CLAUDE) :] if rel.startswith(_LIVE_CLAUDE) else rel


def live_rel(rel: str) -> str:
    return _LIVE_CLAUDE + rel[len(_STORED_CLAUDE) :] if rel.startswith(_STORED_CLAUDE) else rel
