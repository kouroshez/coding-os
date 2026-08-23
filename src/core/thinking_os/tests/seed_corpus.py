"""Deterministic seed corpus shared by the seed-simulation suites.

The three suites read different surfaces of the SAME generated database, so the
generators and the `seeded_conn` fixture live here instead of being duplicated
into each one. Import the fixture by name; pytest resolves it from the importing
module's namespace.
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Seed data constants
# ---------------------------------------------------------------------------

DOMAINS = ["BACKEND", "FRONTEND", "INFRA", "DOCS", "TEST"]
TYPES = ["feat", "fix", "refactor", "docs", "test", "infra"]
OUTCOMES = ["success", "success", "success", "success", "rework", "rework", "partial", "blocked"]
COMPLEXITIES = ["CLEAR", "CLEAR", "COMPLICATED", "COMPLICATED", "COMPLICATED", "COMPLEX"]
MODELS = ["sonnet", "sonnet", "sonnet", "opus", "haiku"]
AGENT_TYPES = ["general", "planner", "code-reviewer", "tdd-guide", "architect", "security-reviewer"]
SKILLS = [
    "python-django",
    "nextjs-react",
    "clean-code",
    "thinking_os",
    "tailwind-design-system",
    "django-tdd",
    "postgres-patterns",
    "bash-linux",
    "api-design-principles",
    "",
]

BACKEND_FILES = [
    "backend/apps/products/models.py",
    "backend/apps/products/views.py",
    "backend/apps/products/serializers.py",
    "backend/apps/products/services.py",
    "backend/apps/orders/models.py",
    "backend/apps/orders/views.py",
    "backend/apps/auth/views.py",
    "backend/apps/auth/services.py",
    "backend/apps/payments/services.py",
    "backend/config/settings/base.py",
]
FRONTEND_FILES = [
    "frontend/src/app/page.tsx",
    "frontend/src/app/layout.tsx",
    "frontend/src/components/ProductCard.tsx",
    "frontend/src/components/Header.tsx",
    "frontend/src/hooks/useCart.ts",
    "frontend/src/lib/api.ts",
    "frontend/src/app/products/[slug]/page.tsx",
    "frontend/src/components/Footer.tsx",
]
INFRA_FILES = [
    "core/scripts/task-done.sh",
    "core/scripts/task-start.sh",
    "core/thinking_os/server.py",
    "core/thinking_os/database.py",
    "Makefile",
    "docker-compose.yml",
    ".github/workflows/ci.yml",
]
DOC_FILES = [
    "docs/PRD/01-overview.md",
    "docs/engineering/backend-rules.md",
    "docs/playbooks/backend-api.md",
    "AGENTS.md",
    "docs/tasks.md",
]

DOMAIN_FILES = {
    "BACKEND": BACKEND_FILES,
    "FRONTEND": FRONTEND_FILES,
    "INFRA": INFRA_FILES,
    "DOCS": DOC_FILES,
    "TEST": BACKEND_FILES,  # tests touch backend files
}

OBSERVATION_TITLES = [
    "Modified {file}",
    "Created {file}",
    "Refactored {file}",
    "Fixed bug in {file}",
    "Added validation to {file}",
    "Updated imports in {file}",
    "Added error handling to {file}",
]

CONCEPTS_POOL = [
    ["django", "model", "orm"],
    ["django", "view", "api"],
    ["react", "component", "hooks"],
    ["react", "ssr", "hydration"],
    ["auth", "security", "jwt"],
    ["payment", "stripe", "webhook"],
    ["testing", "pytest", "coverage"],
    ["migration", "schema", "sql"],
    ["docker", "deploy", "ci"],
    ["docs", "governance", "ssot"],
    ["tailwind", "design", "responsive"],
    ["celery", "async", "queue"],
    ["error-handling", "exception", "logging"],
    ["performance", "cache", "query"],
    ["typescript", "types", "interface"],
    ["nextjs", "routing", "metadata"],
]

# 20 persona descriptions for realistic narratives
PERSONAS = [
    "Senior backend dev doing Django model refactoring",
    "Junior frontend dev learning Next.js Server Components",
    "DevOps engineer setting up CI/CD pipeline",
    "Product manager writing PRD documentation",
    "Security reviewer auditing auth endpoints",
    "QA engineer writing integration tests",
    "Full-stack dev implementing checkout flow",
    "Tech lead reviewing architecture decisions",
    "Data engineer optimizing database queries",
    "Frontend dev implementing design system",
    "Backend dev building payment integration",
    "New hire onboarding to the codebase",
    "Senior dev mentoring via code review",
    "Release manager preparing deployment",
    "Backend dev implementing Celery tasks",
    "Frontend dev fixing hydration errors",
    "DevOps setting up monitoring and alerts",
    "Backend dev building REST API endpoints",
    "Frontend dev implementing responsive layout",
    "Architect planning microservice migration",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_date(start_days_ago: int = 180, end_days_ago: int = 0) -> str:
    """Random ISO datetime within range."""
    delta = random.randint(end_days_ago, start_days_ago)
    dt = datetime.now(timezone.utc) - timedelta(
        days=delta, hours=random.randint(0, 23), minutes=random.randint(0, 59)
    )
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _random_session_id() -> str:
    return f"ses-{random.randint(10000, 99999)}"


def seed_task_outcomes(conn: sqlite3.Connection, count: int = 200) -> list[str]:
    """Seed task_outcomes with realistic distribution."""
    task_ids = []
    # Bias: BACKEND has higher rework rate
    for i in range(1, count + 1):
        task_id = f"TASK-{i:03d}"
        domain = random.choice(DOMAINS)
        task_type = random.choice(TYPES)
        complexity = random.choice(COMPLEXITIES)

        # BACKEND gets 40% rework, others get 15%
        if domain == "BACKEND":
            outcome = random.choice(["success", "success", "rework", "rework", "rework", "partial"])
        elif domain == "FRONTEND":
            outcome = random.choice(
                ["success", "success", "success", "rework", "partial", "partial"]
            )
        else:
            outcome = random.choice(OUTCOMES)

        dims = {"CLEAR": 1, "COMPLICATED": random.choice([2, 3]), "COMPLEX": random.choice([4, 5])}
        model = random.choice(MODELS)
        skills = random.choice(SKILLS)
        created = _random_date()

        conn.execute(
            "INSERT OR REPLACE INTO task_outcomes "
            "(task_id, type, domain, complexity, dimensions, outcome, model, skills_used, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                task_type,
                domain,
                complexity,
                dims.get(complexity, 1),
                outcome,
                model,
                skills,
                created,
            ),
        )
        task_ids.append(task_id)

    conn.commit()
    return task_ids


def seed_observations(conn: sqlite3.Connection, count: int = 500) -> int:
    """Seed observations with realistic file edits."""
    inserted = 0
    sessions = [_random_session_id() for _ in range(30)]

    for _i in range(count):
        domain = random.choice(DOMAINS)
        files = DOMAIN_FILES[domain]
        file_path = random.choice(files)
        tool = random.choice(["Write", "Edit", "Edit", "Edit"])  # Edit is more common
        title_tpl = random.choice(OBSERVATION_TITLES)
        title = title_tpl.format(file=file_path.split("/")[-1])
        concepts = json.dumps(random.choice(CONCEPTS_POOL))
        session = random.choice(sessions)
        narrative = random.choice(PERSONAS)
        impact = round(random.uniform(0.1, 0.9), 2)
        cost = random.randint(50, 2000)
        created = _random_date()

        memory_type_map = {
            "BACKEND": "pattern",
            "FRONTEND": "pattern",
            "INFRA": "workflow",
            "DOCS": "config",
            "TEST": "pattern",
        }

        conn.execute(
            "INSERT INTO observations "
            "(session_id, tool_name, observation_type, memory_type, impact_score, "
            "title, narrative, concepts, files_modified, cost_tokens, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session,
                tool,
                tool.lower(),
                memory_type_map[domain],
                impact,
                title,
                narrative,
                concepts,
                file_path,
                cost,
                created,
            ),
        )
        inserted += 1

    conn.commit()
    return inserted


def seed_agent_metrics(conn: sqlite3.Connection, count: int = 100) -> int:
    """Seed agent_metrics with performance data."""
    for _i in range(count):
        task_id = f"TASK-{random.randint(1, 200):03d}"
        agent = random.choice(AGENT_TYPES)
        model = random.choice(MODELS)
        domain = random.choice(DOMAINS)
        complexity = random.choice(COMPLEXITIES)
        outcome = random.choice(OUTCOMES)
        duration = random.randint(5000, 300000)
        created = _random_date()

        conn.execute(
            "INSERT INTO agent_metrics "
            "(task_id, agent_type, model, duration_ms, domain, complexity, outcome, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, agent, model, duration, domain, complexity, outcome, created),
        )

    conn.commit()
    return count


def seed_sessions(conn: sqlite3.Connection, count: int = 30) -> int:
    """Seed session_summaries."""
    for i in range(count):
        session_id = f"ses-{10000 + i}"
        task_id = f"TASK-{random.randint(1, 200):03d}" if random.random() > 0.2 else None
        created = _random_date()

        conn.execute(
            "INSERT INTO session_summaries "
            "(session_id, task_id, request, investigated, learned, completed, next_steps, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                task_id,
                random.choice(PERSONAS),
                f"Explored {random.choice(DOMAINS).lower()} domain files",
                f"Discovered {random.choice(['performance issue', 'missing validation', 'dead code', 'naming inconsistency'])}",
                f"Fixed {random.randint(1, 5)} issues in {random.choice(DOMAINS).lower()}",
                f"Continue with {random.choice(['testing', 'refactoring', 'documentation', 'deployment'])}",
                created,
            ),
        )

    conn.commit()
    return count
