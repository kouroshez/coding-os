"""Cynefin classification: the deterministic heuristic and its MCP tool.

Pure text analysis plus the gate-marker write. No registry, no bundle, no
database — the one cognition surface the Hub chat router also calls directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from tools._shared import _gated_module, ok, safe_tool

logger = logging.getLogger("coding_os.tools.cognition")


def classify_prompt_heuristic(prompt: str) -> dict:
    """Deterministic Cynefin + dimensions heuristic — shared by the
    cos_classify_prompt tool and the hub chat auto-router (no LLM call)."""
    import re as _re

    text = (prompt or "").strip().lower()
    if not text:
        return {
            "complexity": "CLEAR",
            "dimensions": 1,
            "signals": [],
            "hit_domains": [],
            "reasoning": "empty prompt",
        }

    signals: list[str] = []
    complexity = "CLEAR"

    chaotic_re = _re.compile(
        r"\b(p0|p1|outage|down|broken|crashed?|emergency|urgent|"
        r"fire|on[- ]call|paged|rollback (?:now|asap))\b"
    )
    if chaotic_re.search(text):
        complexity = "CHAOTIC"
        signals.append("incident-language")

    complex_re = _re.compile(
        r"\b(best way|explore|experiment|optimi[sz]e|research|novel|"
        r"investigate|figure out|prototype|spike|trade[- ]off|benchmark)\b"
    )
    if complexity == "CLEAR" and complex_re.search(text):
        complexity = "COMPLEX"
        signals.append("exploratory-language")

    complicated_re = _re.compile(
        r"\b(design|architect|integrate|refactor|implement|build|migrat\w*|"
        r"split|merge|extract|generali[sz]e|extend|orchestrat\w*|"
        r"normali[sz]e|denormali[sz]e)\b"
    )
    if complexity == "CLEAR" and complicated_re.search(text):
        complexity = "COMPLICATED"
        signals.append("design-language")

    word_count = len(text.split())
    if complexity == "CLEAR" and word_count > 60:
        complexity = "COMPLICATED"
        signals.append(f"prompt-length={word_count}")

    domain_patterns = {
        "backend": r"\b(api|backend|server|django|fastapi|fiber|endpoint|router|service)\b",
        "frontend": r"\b(frontend|react|next\.?js|nextjs|component|ui|client|page|jsx|tsx)\b",
        "mobile": r"\b(mobile|ios|android|react native|expo|swift|kotlin)\b",
        "ai": r"\b(llm|ai|prompt|embedding|rag|model|completion|token)\b",
        "security": r"\b(security|auth|permission|csrf|xss|sql injection|jwt|oauth|tls|encryption|secret)\b",
        "ops": r"\b(deploy|ci/cd|docker|kubernetes|k8s|infra|monitoring|alert|runbook|sre)\b",
        "docs": r"\b(doc|documentation|readme|spec|playbook|adr)\b",
        "db": r"\b(database|sql|sqlite|postgres|mysql|migration|schema|index|query)\b",
        "graph": r"\b(graph|neo4j|kuzu|node|edge|traversal)\b",
        "test": r"\b(test|testing|pytest|jest|coverage|fixture|mock)\b",
    }
    hit_domains: list[str] = []
    for name, pat in domain_patterns.items():
        if _re.search(pat, text):
            hit_domains.append(name)
    dimensions = max(1, len(hit_domains))
    if dimensions >= 5 and complexity == "CLEAR":
        complexity = "COMPLICATED"
        signals.append(f"multi-dimension={dimensions}")

    trivial_re = _re.compile(r"^(fix typo|update doc(?:string)?|tweak (?:wording|comment))\b")
    if (
        trivial_re.search(text)
        and word_count < 15
        and len(hit_domains) <= 1
        and complexity != "CHAOTIC"
    ):
        complexity = "CLEAR"
        dimensions = 1
        signals = ["trivial-edit-shortcut"]

    reasoning = (
        f"Cynefin: {complexity} ({', '.join(signals) or 'no escalating signals'}); "
        f"dims={dimensions} from domains: {', '.join(hit_domains) or 'none'}"
    )
    return {
        "complexity": complexity,
        "dimensions": dimensions,
        "signals": signals,
        "hit_domains": hit_domains,
        "reasoning": reasoning,
    }


def register_cos_classify_prompt(mcp, db_path):
    """Register cos_classify_prompt — heuristic Cynefin + dimensions classifier.

    Replaces the manual `bash write-state.sh .thinking_os-gate "COMPLICATED 3"`
    step. The agent calls this on the user's prompt and gets back a recorded
    gate without manually counting domains or evaluating Cynefin signals.
    """

    @mcp.tool(
        name="cos_classify_prompt",
        description=(
            "Heuristic Cynefin + dimensions classifier. Reads a user prompt "
            "and returns {complexity, dimensions, reasoning, signals}. "
            "Optionally writes the gate marker so enforce-task-start.sh "
            "passes. Replaces the manual `write-state.sh .thinking_os-gate` "
            "step. Sub-second; deterministic; no LLM call."
        ),
    )
    @safe_tool
    def cos_classify_prompt(
        prompt: str,
        record: bool = True,
        agent_dir: str = "",
    ) -> str:
        import os as _os

        if not (prompt or "").strip():
            return ok(
                {
                    "complexity": "CLEAR",
                    "dimensions": 1,
                    "reasoning": "empty prompt",
                    "signals": [],
                    "recorded": False,
                },
                meta={"layer": "routing"},
            )

        heuristic = classify_prompt_heuristic(prompt)
        complexity = heuristic["complexity"]
        dimensions = heuristic["dimensions"]
        signals = heuristic["signals"]
        hit_domains = heuristic["hit_domains"]
        reasoning = heuristic["reasoning"]

        # Record the gate so enforce-task-start.sh passes — but ONLY when a
        # panel session is resolvable. The MCP server has no per-call panel
        # env, so this succeeds mainly when COS_PANEL_DIR is set (or agent_dir
        # is a real panel dir). It writes the SAME session-prefixed format the
        # strict panel reader (check-state.sh) requires; a bare
        # value or an agent-dir write would be silently rejected and leave a
        # misleading fossil — so we do neither, reporting recorded=false + a
        # shell hint instead. (Fixes the prior wrong-dir/wrong-format
        # /no-trace bug.)
        recorded = False
        record_hint = ""
        if record:
            panel_dir = _os.environ.get("COS_PANEL_DIR") or agent_dir
            sid = ""
            if panel_dir:
                sid_file = Path(panel_dir) / "session-id"
                if sid_file.exists():
                    try:
                        sid = sid_file.read_text(encoding="utf-8").strip().split(" ")[0]
                    except OSError:
                        sid = ""
            if panel_dir and sid:
                try:
                    gate_path = Path(panel_dir) / ".thinking_os-gate"
                    gate_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = gate_path.with_name(".thinking_os-gate.tmp")
                    tmp_path.write_text(f"{sid} {complexity} {dimensions}\n", encoding="utf-8")
                    tmp_path.replace(gate_path)
                    recorded = True
                    try:
                        import tracing

                        tracing.emit(
                            sid,
                            "classify",
                            {"complexity": complexity, "dimensions": dimensions},
                        )
                    except Exception as exc:
                        from core.logging_os import swallow_safe

                        swallow_safe("thinking_os.cognition", "classify trace emit failed", exc=exc)
                except OSError:
                    recorded = False
            if not recorded:
                record_hint = (
                    "gate not recorded (no panel session context from MCP); "
                    "record it in your shell: write-state.sh .thinking_os-gate "
                    f'"{complexity} {dimensions}"'
                )

        # Discoverability nudge (TASK-509): a COMPLICATED+ gate needs the
        # cognition surface (role composition / formula dispatch, Rule 15), but a
        # lean profile may have disabled it. Surface the one-liner to re-enable
        # rather than letting the agent hit a module_disabled wall mid-plan.
        nudge = ""
        if (
            complexity in ("COMPLICATED", "COMPLEX")
            and _gated_module("cos_compose_chain") == "cognition"
        ):
            nudge = (
                f"{complexity} work but the cognition module is OFF — role "
                "composition / formula dispatch are unavailable. Enable it with "
                "`cos module enable cognition` (or scaffold with `--profile full`)."
            )

        return ok(
            {
                "complexity": complexity,
                "dimensions": dimensions,
                "reasoning": reasoning,
                "signals": signals,
                "domains": hit_domains,
                "recorded": recorded,
                "record_hint": record_hint,
                "nudge": nudge,
            },
            meta={"layer": "routing"},
        )

    return cos_classify_prompt
