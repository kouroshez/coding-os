"""Formula Composer — prompt keyword heuristics."""

from __future__ import annotations

from cognition_schemas import TaskSignals

# Action keyword → TaskSignals.action. Order matters: earlier wins on a tie
# (debug/audit/review beat the generic create/modify so a "fix the failing
# test" prompt routes to debugger, not implementer). English keyword match;
# the agent's own comprehension covers prompts in other languages.
_ACTION_PATTERNS: list[tuple[str, str]] = [
    (
        "debug",
        r"\b(debug|diagnose|root[- ]?cause|stack[- ]?trace|failing|broken|crash)\b",
    ),
    ("audit", r"\b(audit|security review|pentest|vulnerab|cve|threat model)\b"),
    ("review", r"\b(review|code[- ]?review|critique|assess)\b"),
    (
        "research",
        r"\b(research|investigate|explore|best way|compare|evaluate|spike)\b",
    ),
    ("refactor", r"\b(refactor|clean ?up|restructure|simplify|deduplicate)\b"),
    ("document", r"\b(document\w*|write docs|readme|changelog|adr)\b"),
    ("deploy", r"\b(deploy|release|ship|rollout|ci/cd|pipeline)\b"),
    ("create", r"\b(add|create|implement|build|new |feature)\b"),
    ("modify", r"\b(fix|update|change|modify|edit|adjust|tweak)\b"),
]

# Domain keyword → TaskSignals.domain entries. Mirrors cos_classify_prompt's
# domain_patterns (kept in sync; that tool sets the gate, this sets the chain).
_DOMAIN_PATTERNS: dict[str, str] = {
    "security": r"\b(security|auth|permission|csrf|xss|sql injection|jwt|oauth|tls|encryption|secret)\b",
    "backend": r"\b(api|backend|server|django|fastapi|fiber|endpoint|router|service|mcp tool)\b",
    "frontend": r"\b(frontend|react|next\.?js|nextjs|component|ui|client|page|jsx|tsx)\b",
    "db": r"\b(database|sql|sqlite|postgres|mysql|migration|schema|index|query)\b",
    "infra": r"\b(deploy|ci/cd|docker|kubernetes|k8s|infra|hook|registry|adapter)\b",
    "docs": r"\b(doc|documentation|readme|spec|playbook|adr)\b",
    "graph": r"\b(graph|node|edge|traversal|extractor)\b",
}


def signals_from_prompt(
    prompt: str,
    complexity: str = "COMPLICATED",
    dimensions: int = 1,
) -> TaskSignals:
    """Build a RICH TaskSignals from raw prompt text.

    The auto-compose hook previously passed only complexity+dimensions, leaving
    action='unknown' / domain=[] — under which only `analyst` ever clears its
    min_score, so every task composed the identical ['analyst'] chain. This
    derives action, domain, scope_size, novelty, urgency from the prompt so the
    composer can actually discriminate (debug→debugger, security→security_auditor,
    docs→documenter, …). Deterministic; no LLM call. (TASK-057)
    """
    import re as _re

    text = (prompt or "").strip().lower()
    action = "unknown"
    for act, pat in _ACTION_PATTERNS:
        if _re.search(pat, text):
            action = act
            break

    domains = [name for name, pat in _DOMAIN_PATTERNS.items() if _re.search(pat, text)]

    # scope_size from prompt length + breadth keywords.
    words = len(text.split())
    if _re.search(r"\b(everywhere|all |every |entire|whole|across)\b", text) or words > 200:
        scope_size = "large"
    elif words < 12:
        scope_size = "small"
    else:
        scope_size = "medium"

    novelty = (
        0.6
        if action == "research"
        or _re.search(r"\b(novel|unknown|first time|from scratch|greenfield)\b", text)
        else 0.0
    )
    urgency = (
        "incident"
        if _re.search(r"\b(p0|p1|outage|down|emergency|urgent|asap|hotfix)\b", text)
        else "normal"
    )
    has_unknowns = bool(_re.search(r"\b(unknown|not sure|unclear|investigate)\b", text))

    return TaskSignals(
        complexity=complexity
        if complexity in {"CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC", "CONFUSION"}
        else "COMPLICATED",
        dimensions=max(1, dimensions),
        action=action,  # type: ignore[arg-type]
        domain=domains,
        scope_size=scope_size,  # type: ignore[arg-type]
        novelty=novelty,
        urgency=urgency,  # type: ignore[arg-type]
        has_unknowns=has_unknowns,
    )
