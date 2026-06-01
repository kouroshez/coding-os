"""Auto-compose a role chain + surface recall from the recorded complexity gate.

Called by auto-compose-roles.sh (UserPromptSubmit). Reads the panel's
.thinking_os-gate (CLASS DIMS), and for COMPLICATED/COMPLEX classifications:

  1. composes a role chain via formula_composer and stamps .roles/.role so the
     Hub Roles panel + the session banner reflect real activity — closing the
     dead-trigger gap where cos_compose_chain was never auto-invoked (TASK-055);
  2. runs learn_suggest and writes the hits to .learn-suggestions so the Orient
     recall arc fires automatically and remind-learn-validate stops no-opping
     on an empty input (the read-back half of the learning loop).

Prints one context line per produced signal (roles + recall); prints nothing
on any miss/error (the hook always exits 0).

USAGE
    python3 auto_compose.py <gate_class> <gate_dims> <agent_dir>
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("auto_compose")

# formula_composer + cognition_schemas + roles_state live flat under
# src/core/thinking_os; learning lives under thinking_os/tools. Resolve both
# through the hook symlink.
_THIS = Path(__file__).resolve()
_THINKING_OS = _THIS.parents[2] / "thinking_os"
for _p in (_THINKING_OS, _THINKING_OS / "tools"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_COMPOSE_CLASSES = {"COMPLICATED", "COMPLEX"}


def _compose_roles(gate_class: str, dims: int, agent_dir: str | None) -> str:
    """Compose + stamp the role chain. Returns a context line ('' on miss)."""
    try:
        import formula_composer
        import roles_state
        from cognition_schemas import TaskSignals
    except ImportError as exc:
        logger.debug("auto_compose role imports unavailable: %s", exc)
        return ""
    try:
        signals = TaskSignals(complexity=gate_class, dimensions=max(1, dims))
        chain = formula_composer.compose_chain(signals=signals)
    except Exception as exc:  # composer must never break the prompt hook
        logger.debug("compose_chain failed: %s", exc)
        return ""
    if not chain.chain:
        return ""
    roles_state.stamp_roles(chain.chain, agent_dir)
    lead = chain.chain[0]
    rest = len(chain.chain) - 1
    suffix = f"+{rest}" if rest > 0 else ""
    return f"[roles] auto-composed: {lead}{suffix} ({chain.source}) → {' → '.join(chain.chain)}"


def _recall_patterns(gate_class: str, agent_dir: str | None) -> str:
    """Run learn_suggest, write .learn-suggestions, return a recall line.

    Closes the recall arc: surfaces learned patterns into the Orient phase and
    populates .learn-suggestions so remind-learn-validate (task-done) has input
    to validate against. Domain is left None — the gate alone doesn't carry it,
    and learn_suggest's domain-agnostic branch matches all patterns.
    """
    import sqlite3

    db_path = os.environ.get("COS_DB_PATH") or str(
        Path(os.environ.get("COS_STATE_DIR", ".coding-os")) / "coding-os.db"
    )
    if not Path(db_path).exists():
        return ""
    try:
        from learning import learn_suggest
    except ImportError as exc:
        logger.debug("learn_suggest import unavailable: %s", exc)
        return ""
    try:
        conn = sqlite3.connect(db_path, timeout=3)
        conn.row_factory = sqlite3.Row
        try:
            result = learn_suggest(conn, complexity=gate_class, limit=5)
        finally:
            conn.close()
    except Exception as exc:  # recall must never break the prompt hook
        logger.debug("learn_suggest failed: %s", exc)
        return ""

    suggestions = result.get("suggestions") or []
    if not suggestions:
        return ""

    target_dir = agent_dir or os.environ.get("COS_AGENT_DIR") or str(
        Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
        / os.environ.get("COS_AGENT", "claude")
    )
    lines: list[str] = []
    for s in suggestions:
        pid = s.get("id")
        if pid is None:
            continue
        txt = (s.get("pattern") or "").replace("\t", " ").replace("\n", " ")
        lines.append(f"{pid}\t{txt}")
    if not lines:
        return ""
    try:
        target = Path(target_dir) / ".learn-suggestions"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        logger.debug(".learn-suggestions write failed: %s", exc)

    top = suggestions[0]
    top_txt = (top.get("pattern") or "")[:70]
    more = len(suggestions) - 1
    suffix = f" (+{more} more)" if more > 0 else ""
    return f"[recall] {len(suggestions)} learned pattern(s) — validate via cos_learn_validate. Top: {top_txt}{suffix}"


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    gate_class = (argv[1] or "").upper()
    if gate_class not in _COMPOSE_CLASSES:
        return 0
    try:
        dims = int(argv[2])
    except (ValueError, TypeError):
        dims = 1
    agent_dir = argv[3] if len(argv) > 3 and argv[3] else None

    out_lines = [
        line
        for line in (
            _compose_roles(gate_class, dims, agent_dir),
            _recall_patterns(gate_class, agent_dir),
        )
        if line
    ]
    if out_lines:
        print("\n".join(out_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
