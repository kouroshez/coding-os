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
