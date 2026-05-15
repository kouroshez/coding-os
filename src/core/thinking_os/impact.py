"""
Thinking OS — Impact scoring (digital amygdala) (TASK-157).

Shared module for calculating impact_score (0.0-1.0) from file paths,
tool names, domains, and outcomes. High-impact memories resist forgetting
and rank higher in search.

Used by: capture.py, record_outcome.py, decay.py, memory.py search
"""

from __future__ import annotations


# File path patterns that increase impact.
# Covers Python/Django (models, views, urls, serializers, migrations),
# Node/Next.js (route, middleware, server actions), Go (main, handler),
# infra (Dockerfile, Makefile, terraform, CI config), core/ kernel files
# the meta-project itself dog-foods, and every variant of the secret-
# bearing `.env`.  Any additional token earns +0.15 up to the 1.0 cap.
HIGH_IMPACT_PATTERNS = [
    # Python / Django / DRF
    "models.py", "schema", "migration", "settings", "auth",
    "payment", "security", "permission", "middleware", ".env",
    "views.py", "urls.py", "serializers.py", "tasks.py", "celery",
    # Frontend / Next.js / React
    "route.ts", "route.tsx", "layout.tsx", "middleware.ts",
    "server-actions", "api/", "_app.", "_document.",
    # Go / Fiber
    "main.go", "handler.go", "middleware.go",
    # Infra / CI / IaC
    "Dockerfile", "docker-compose", "Makefile", "terraform", ".github/workflows",
    "pyproject.toml", "package.json",
    # Coding-OS kernel — meta-project treats these as load-bearing
    "core/thinking_os/", "core/hooks/", "core/rules/", "core/skills/",
    "adapters/", "cli/",
]

# File path patterns that decrease impact
LOW_IMPACT_PATTERNS = [
    "test_", "tests/", "README", "__pycache__", ".pyc",
    "fixtures/", "mock", "conftest", ".snap", ".svg",
    "/.venv/", "/node_modules/", "CHANGELOG", ".log",
]

# Domain boosts
DOMAIN_BOOSTS = {
    "SECURITY": 0.2,
    "PAYMENTS": 0.2,
    "AUTH": 0.15,
}

# Outcome boosts (retroactive amygdala tagging)
OUTCOME_BOOSTS = {
    "rework": 0.3,
    "blocked": 0.2,
    "partial": 0.1,
    "success": 0.0,
}


def calculate_impact(
    *,
    file_path: str = "",
    tool_name: str = "",
    domain: str = "",
    outcome: str = "",
) -> float:
    """Calculate impact score for an observation or pattern.

    The digital amygdala: tags experiences with emotional weight.
    High-impact memories decay slower, rank higher in search,
    and need fewer occurrences for pattern extraction.

    Args:
        file_path: Path of the modified file.
        tool_name: Tool used (Write/Edit).
        domain: Task domain (BACKEND/FRONTEND/etc).
        outcome: Task outcome (success/rework/partial/blocked).

    Returns:
        Impact score between 0.0 and 1.0.
    """
    score = 0.5  # base

    # File path analysis
    path_lower = file_path.lower()
    for pattern in HIGH_IMPACT_PATTERNS:
        if pattern in path_lower:
            score += 0.15
    for pattern in LOW_IMPACT_PATTERNS:
        if pattern in path_lower:
            score -= 0.1

    # Domain boost
    domain_upper = domain.upper()
    for domain_key, boost in DOMAIN_BOOSTS.items():
        if domain_key in domain_upper:
            score += boost

    # Outcome boost (retroactive)
    if outcome:
        score += OUTCOME_BOOSTS.get(outcome, 0.0)

    # Multiple file patterns compound but stay bounded
    return round(max(0.1, min(1.0, score)), 2)


def calculate_pattern_impact(observation_scores: list[float]) -> float:
    """Calculate pattern impact as average of source observation impacts.

    Args:
        observation_scores: List of impact_scores from source observations.

    Returns:
        Average impact score, or 0.5 if no scores.
    """
    if not observation_scores:
        return 0.5
    return round(sum(observation_scores) / len(observation_scores), 2)
