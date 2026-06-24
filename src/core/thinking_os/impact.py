"""Impact scoring (digital amygdala): impact_score in [0.0, 1.0] from file path,
tool, domain, and outcome — high-impact memories decay slower and rank higher.
Used by capture.py, record_outcome.py, decay.py, memory.py."""

from __future__ import annotations

# Each matched pattern adds +0.15 (capped at 1.0). Category labels are navigational.
HIGH_IMPACT_PATTERNS = [
    # Python / Django / DRF
    "models.py",
    "schema",
    "migration",
    "settings",
    "auth",
    "payment",
    "security",
    "permission",
    "middleware",
    ".env",
    "views.py",
    "urls.py",
    "serializers.py",
    "tasks.py",
    "celery",
    # Frontend / Next.js / React
    "route.ts",
    "route.tsx",
    "layout.tsx",
    "middleware.ts",
    "server-actions",
    "api/",
    "_app.",
    "_document.",
    # Go / Fiber
    "main.go",
    "handler.go",
    "middleware.go",
    # Infra / CI / IaC
    "Dockerfile",
    "docker-compose",
    "Makefile",
    "terraform",
    ".github/workflows",
    "pyproject.toml",
    "package.json",
    # Coding-OS kernel — meta-project treats these as load-bearing
    "core/thinking_os/",
    "core/hooks/",
    "core/rules/",
    "core/skills/",
    "adapters/",
    "cli/",
]

LOW_IMPACT_PATTERNS = [
    "test_",
    "tests/",
    "README",
    "__pycache__",
    ".pyc",
    "fixtures/",
    "mock",
    "conftest",
    ".snap",
    ".svg",
    "/.venv/",
    "/node_modules/",
    "CHANGELOG",
    ".log",
]

DOMAIN_BOOSTS = {
    "SECURITY": 0.2,
    "PAYMENTS": 0.2,
    "AUTH": 0.15,
}

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
    """Impact score in [0.0, 1.0]: high-impact experiences decay slower and need fewer occurrences to form a pattern."""
    score = 0.5

    path_lower = file_path.lower()
    for pattern in HIGH_IMPACT_PATTERNS:
        if pattern in path_lower:
            score += 0.15
    for pattern in LOW_IMPACT_PATTERNS:
        if pattern in path_lower:
            score -= 0.1

    domain_upper = domain.upper()
    for domain_key, boost in DOMAIN_BOOSTS.items():
        if domain_key in domain_upper:
            score += boost

    if outcome:
        score += OUTCOME_BOOSTS.get(outcome, 0.0)

    return round(max(0.1, min(1.0, score)), 2)


def calculate_pattern_impact(observation_scores: list[float]) -> float:
    """Pattern impact = mean of source observation impacts, or 0.5 if none."""
    if not observation_scores:
        return 0.5
    return round(sum(observation_scores) / len(observation_scores), 2)
