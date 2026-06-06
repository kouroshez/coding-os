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
# src/core/thinking_os; learning lives in the thinking_os.tools PACKAGE.
# Add ONLY thinking_os to sys.path and import learning package-qualified
# (from tools.learning, below). Adding thinking_os/tools flat would put it
# AHEAD of thinking_os, so a bare `import cognition` (tools/cognition.py::_cog)
# could shadow to tools/cognition.py instead of the top-level cognition.py that
# owns load_situation_registry — the cross-process shadow bug.
_THIS = Path(__file__).resolve()
_THINKING_OS = _THIS.parents[2] / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

_COMPOSE_CLASSES = {"COMPLICATED", "COMPLEX"}


def _session_id(panel_dir: str | None) -> str:
    """Resolve the current session id for trace correlation.

    Reads the per-panel ``session-id`` file (panel_dir is the hook's
    COS_PANEL_DIR), falling back to the env panel/agent dirs then COS_PANEL_ID.
    """
    for base in (panel_dir, os.environ.get("COS_PANEL_DIR"), os.environ.get("COS_AGENT_DIR")):
        if not base:
            continue
        try:
            p = Path(base) / "session-id"
            if p.is_file():
                sid = p.read_text(encoding="utf-8").strip()
                if sid:
                    return sid
        except OSError:
            continue
    return os.environ.get("COS_PANEL_ID") or "auto"


def _lead_directive(lead: str, max_lines: int = 2) -> str:
    """First <=max_lines of the lead role's prompt_prefix — real in-session
    guidance, not just a label. Reuses formula_composer.load_roles (cached).
    Fail-open to '' so the nudge degrades to the chain label on any error.
    """
    try:
        import formula_composer

        meta = formula_composer.load_roles().get(lead, {})
        prefix = (meta.get("prompt_prefix") or "").strip()
        if not prefix:
            return ""
        lines = [ln.strip() for ln in prefix.splitlines() if ln.strip()]
        return " ".join(lines[:max_lines])
    except Exception as exc:
        logger.debug("lead directive unavailable: %s", exc)
        return ""


def _compose_roles(gate_class: str, dims: int, agent_dir: str | None, prompt: str) -> str:
    """Compose + stamp the role chain. Returns a context line ('' on miss).

    Builds a RICH TaskSignals from the prompt (action/domain/scope) so the
    chain actually varies per task instead of collapsing to ['analyst'] for
    every COMPLICATED/COMPLEX prompt (TASK-057).
    """
    try:
        import formula_composer
        import roles_state
    except ImportError as exc:
        logger.debug("auto_compose role imports unavailable: %s", exc)
        return ""
    try:
        signals = formula_composer.signals_from_prompt(prompt, gate_class, max(1, dims))
        chain = formula_composer.compose_chain(signals=signals)
    except Exception as exc:  # composer must never break the prompt hook
        logger.debug("compose_chain failed: %s", exc)
        return ""
    if not chain.chain:
        return ""
    roles_state.stamp_roles(chain.chain, agent_dir)
    # Emit the compose_done trace the Hub /api/roles panel reads. Markers
    # (.roles/.role) are per-panel for the banner; the trace goes agent-level
    # (record_compose_traces passes agent_dir=None → $COS_AGENT_DIR) so the
    # panel — which scans the agent-level traces dir — actually finds it.
    # Without this the auto-compose path was invisible to the panel.
    roles_state.record_compose_traces(chain, _session_id(agent_dir))
    lead = chain.chain[0]
    rest = len(chain.chain) - 1
    suffix = f"+{rest}" if rest > 0 else ""
    line = f"[roles] auto-composed: {lead}{suffix} ({chain.source}) → {' → '.join(chain.chain)}"
    # Append the lead role's directive so the nudge actually GUIDES the agent
    # in-session, not just labels the chain. Token-cheap (lead only).
    directive = _lead_directive(lead)
    if directive:
        line += f"\n[role:{lead}] {directive}"
    return line


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
        from tools.learning import learn_suggest
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

    target_dir = (
        agent_dir
        or os.environ.get("COS_AGENT_DIR")
        or str(
            Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
            / os.environ.get("COS_AGENT", "claude")
        )
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
    # Prompt arrives on stdin (the hook pipes the user prompt) so the composer
    # gets real action/domain signals. Empty stdin → degenerate-but-safe.
    prompt = ""
    try:
        if not sys.stdin.isatty():
            prompt = sys.stdin.read(8192)
    except (OSError, ValueError):
        prompt = ""

    out_lines = [
        line
        for line in (
            _compose_roles(gate_class, dims, agent_dir, prompt),
            _recall_patterns(gate_class, agent_dir),
        )
        if line
    ]
    if out_lines:
        print("\n".join(out_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
