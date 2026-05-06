"""Cross-language lock-in: backend AgentPresence literals ↔ frontend visuals."""
from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Backend source: the board.py enum.  We extract these from the union
# in the AgentPresence type declaration in types.ts so the test fails
# loudly if someone introduces a new state on one side only.
_TYPES_TS = _REPO_ROOT / "core" / "web" / "ui" / "src" / "features" / "cos-board" / "types.ts"
_VISUALS_TS = _REPO_ROOT / "core" / "web" / "ui" / "src" / "features" / "cos-board" / "agentPresenceVisuals.ts"
_BOARD_PY = _REPO_ROOT / "core" / "web" / "routes" / "board.py"


def _extract_ts_union(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+type\s+AgentPresence\s*=\s*([^;]+);",
        src,
    )
    assert m, f"AgentPresence type not found in {path}"
    return {
        s.strip().strip("'").strip('"')
        for s in m.group(1).split("|")
        if s.strip()
    }


def _extract_visual_keys(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    m = re.search(
        r"AGENT_PRESENCE_VISUALS\s*:\s*Record<AgentPresence,\s*AgentVisual>\s*=\s*\{(.*?)\n\};",
        src,
        re.DOTALL,
    )
    assert m, f"AGENT_PRESENCE_VISUALS object literal not found in {path}"
    body = m.group(1)
    # Top-level keys: `  <key>: { ... },`
    return {m.group(1) for m in re.finditer(r"^\s*([a-zA-Z_]+)\s*:\s*\{", body, re.MULTILINE)}


def _extract_backend_states(path: Path) -> set[str]:
    """Pull the states board.py can return from _agent_state / _presence_state."""
    src = path.read_text(encoding="utf-8")
    # Every `return "<state>"` or `best = "<state>"` inside board.py that
    # feeds _agent_state's contract.
    states: set[str] = set()
    for m in re.finditer(r'return\s+"(active|present|offline)"', src):
        states.add(m.group(1))
    for m in re.finditer(r'best\s*=\s*"(active|present|offline)"', src):
        states.add(m.group(1))
    return states


def test_frontend_visual_keys_match_agent_presence_union():
    union = _extract_ts_union(_TYPES_TS)
    keys = _extract_visual_keys(_VISUALS_TS)
    assert union == keys, (
        "Drift between types.ts::AgentPresence and "
        "agentPresenceVisuals.ts::AGENT_PRESENCE_VISUALS.\n"
        f"  union only : {sorted(union - keys)}\n"
        f"  visuals only: {sorted(keys - union)}"
    )


def test_backend_states_are_subset_of_frontend_union():
    """Every state board.py emits must be renderable by the SPA."""
    union = _extract_ts_union(_TYPES_TS)
    states = _extract_backend_states(_BOARD_PY)
    missing = states - union
    assert not missing, (
        f"board.py emits state(s) {sorted(missing)!r} that AgentPresence "
        f"doesn't know about. Update types.ts + agentPresenceVisuals.ts."
    )


def test_frontend_visual_entries_are_complete():
    """Each visual entry must declare color / ring / pulse / label."""
    src = _VISUALS_TS.read_text(encoding="utf-8")
    # Find each top-level key block and verify the four required fields
    # appear inside it.  Simple line-scan is enough given the file's shape.
    for key in _extract_visual_keys(_VISUALS_TS):
        # Grab the slice between "<key>: {" and the next top-level "},"
        block_match = re.search(
            rf"{re.escape(key)}:\s*\{{(.*?)\}},",
            src,
            re.DOTALL,
        )
        assert block_match, f"{key} block not parseable"
        block = block_match.group(1)
        for field in ("color", "ring", "pulse", "label"):
            assert f"{field}:" in block, f"{key} missing field {field!r}"
