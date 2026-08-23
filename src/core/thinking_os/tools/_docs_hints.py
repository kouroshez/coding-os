"""Query-time heuristics for `cos_doc_search`.

Two soft signals that narrow the chunk universe before ranking: what the query
text itself implies (a code-shaped token routes to FTS first, "this quarter"
implies a date floor, "jwt" implies the SECURITY domain) and what the active
task implies (its swimlane maps to a default domain). Both are suggestions an
explicit argument always overrides — never a hard filter.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("coding_os.tools.docs")


# G.7.3 — identifier-looking query detection. Heuristic is deliberately
# permissive: if the user typed something code-shaped we route to FTS first
# because cosine similarity is weak on short literal tokens.
_IDENTIFIER_RE = re.compile(
    r"("
    r"[A-Za-z_][A-Za-z0-9_]*\(\)"  # function call syntax
    r"|[a-z]+(?:_[a-z0-9]+)+"  # snake_case (2+ segments)
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"  # CamelCase (2+ segments)
    r"|TASK-\d+"  # task id
    r"|`[^`]+`"  # explicit backtick identifier
    r"|[a-zA-Z_][a-zA-Z0-9_]*\.py|\.ts|\.tsx|\.md"  # file with known ext
    r")"
)


def looks_like_identifier(query: str) -> bool:
    """Return True when `query` contains a code-shaped token."""
    if not query or not query.strip():
        return False
    return bool(_IDENTIFIER_RE.search(query))


SearchMode = Literal["auto", "semantic", "lexical"]


# ---------------------------------------------------------------------------
# Stage-1 metadata heuristics — query-time hint extraction + active-task context
# ---------------------------------------------------------------------------

# Domain hints — keyword → canonical domain. Conservative: only fire on
# unambiguous tokens. Extending: keep mapping data-driven (no logic in
# the regex), agents can override by passing domain= explicitly.
_DOMAIN_HINTS: dict[str, str] = {
    r"\bbackend\b|\bapi\b|\bhandler\b|\bendpoint\b|\bdjango\b|\bfastapi\b|\bfiber\b": "BACKEND",
    r"\bfrontend\b|\breact\b|\bnext\.?js\b|\bcomponent\b|\bpage\b|\bjsx\b|\btsx\b": "FRONTEND",
    r"\bauth\b|\boauth\b|\bjwt\b|\bsecret\b|\bsecurity\b|\bcsrf\b|\bxss\b": "SECURITY",
    r"\bdeploy\b|\bci/cd\b|\bdocker\b|\bk8s\b|\bkubernetes\b|\binfra\b|\brunbook\b": "OPS",
    r"\bllm\b|\bprompt\b|\bembedding\b|\brag\b|\bmodel\b|\btoken\b": "AI",
    r"\bmigration\b|\bsqlite\b|\bschema\b|\bdb\b|\bsql\b|\bquery\b|\bindex\b": "CORE",
    r"\bgraph\b|\bnode\b|\bedge\b|\bkuzu\b": "CORE",
    r"\bhook\b|\bregistry\b|\badapter\b|\bskill\b": "CORE",
}

# Layer hints — phrasing patterns → frontmatter layer value.
_LAYER_HINTS: dict[str, str] = {
    r"\b(?:adr|architecture decision)\b": "adr",
    r"\bplaybook\b|\bhow to\b|\bworkflow\b|\bprocedure\b": "playbook",
    r"\brunbook\b|\bincident\b|\balert\b|\bon[- ]call\b": "runbook",
    r"\bpost[- ]?mortem\b|\bretrospective\b|\bpostmortem\b": "postmortem",
    r"\bspec\b|\bcontract\b|\bschema\b|\bapi contract\b": "spec",
    r"\bpolicy\b|\brule\b|\bstandard\b": "policy",
}

# Recency hints — phrasing → days lookback. "Recent" is the loosest;
# explicit quarter / month is tightest.
_RECENCY_HINTS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\bthis week\b|\btoday\b|\byesterday\b", re.I), 7),
    (re.compile(r"\bthis month\b|\bthis sprint\b", re.I), 30),
    (re.compile(r"\bthis quarter\b|\bQ[1-4]\b", re.I), 90),
    (re.compile(r"\brecent\b|\blatest\b|\bcurrent\b|\bnow\b", re.I), 90),
]

# Explicit ISO year / date hints — "since 2026", "2025 Q4 …", "after 2024-06".
_YEAR_RE = re.compile(r"\b(?:since|after|from)\s+(20\d{2})(?:-(\d{2}))?(?:-(\d{2}))?\b", re.I)
_BARE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _suggest_filters_from_query(query: str) -> dict[str, Any]:
    if not query:
        return {}
    text = query.lower()
    out: dict[str, Any] = {}

    # Domain hint — first match wins.
    for pat, dom in _DOMAIN_HINTS.items():
        if re.search(pat, text):
            out["suggested_domain"] = dom
            break

    # Layer hint — first match wins.
    for pat, layer in _LAYER_HINTS.items():
        if re.search(pat, text):
            out["suggested_layer"] = layer
            break

    # Recency: explicit "since YYYY[-MM[-DD]]" wins over phrasing.
    yr_match = _YEAR_RE.search(query)
    if yr_match:
        y, m, d = yr_match.group(1), yr_match.group(2) or "01", yr_match.group(3) or "01"
        out["suggested_since_iso"] = f"{y}-{m}-{d}"
    else:
        for rx, days in _RECENCY_HINTS:
            if rx.search(query):
                cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
                out["suggested_since_iso"] = cutoff.isoformat()
                break
        # Bare 4-digit year — only if no recency phrasing already won.
        if "suggested_since_iso" not in out:
            bare = _BARE_YEAR_RE.search(query)
            if bare:
                out["suggested_since_iso"] = f"{bare.group(1)}-01-01"

    return out


# Swimlane → frontmatter domain. Coarse mapping; agent can override with
# explicit domain=. Missing swimlanes leave domain unset.
_SWIMLANE_DOMAIN: dict[str, str] = {
    "core": "CORE",
    "backend": "BACKEND",
    "be": "BACKEND",
    "frontend": "FRONTEND",
    "fe": "FRONTEND",
    "ai": "AI",
    "ops": "OPS",
    "infra": "OPS",
    "security": "SECURITY",
    "docs": "DOCS",
}


def _active_task_context() -> dict[str, str]:
    agent_dir_str = os.environ.get("COS_AGENT_DIR", "")
    if not agent_dir_str:
        return {}
    agent_dir = Path(agent_dir_str)
    out: dict[str, str] = {}
    swim_path = agent_dir / ".swimlane"
    if swim_path.exists():
        try:
            swim = swim_path.read_text(encoding="utf-8").strip().lower()
            if swim and swim in _SWIMLANE_DOMAIN:
                out["domain"] = _SWIMLANE_DOMAIN[swim]
        except OSError as exc:
            logger.debug("active-task swimlane read failed: %s", exc)
    return out
