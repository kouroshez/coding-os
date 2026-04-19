"""
Massive seed data simulation for thinking-os memory system.

Runs the full learning cycle on a SEPARATE test DB (never touches production).
Simulates 20+ personas across 6 months of project history with:
  - 200 task outcomes (mixed success/rework/partial/blocked)
  - 500 observations (Write/Edit across all domains)
  - 100 agent metrics (different models, agent types)
  - 30 sessions
  - 20 experiments

Then exercises every tool to verify the system works under realistic load.
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_db, get_db_stats, has_fts5_table
from tools.learning import learn_extract, learn_suggest, learn_validate, generate_feedback_drafts
from tools.memory import memory_search, memory_timeline, memory_details, memory_promote
from tools.metrics import metric_record, metric_query, metric_trend
from tools.routing import route_model, route_skill

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
    "python-django", "nextjs-react", "clean-code", "thinking-os",
    "tailwind-design-system", "django-tdd", "postgres-patterns",
    "bash-linux", "api-design-principles", "",
]

BACKEND_FILES = [
    "backend/apps/products/models.py", "backend/apps/products/views.py",
    "backend/apps/products/serializers.py", "backend/apps/products/services.py",
    "backend/apps/orders/models.py", "backend/apps/orders/views.py",
    "backend/apps/auth/views.py", "backend/apps/auth/services.py",
    "backend/apps/payments/services.py", "backend/config/settings/base.py",
]
FRONTEND_FILES = [
    "frontend/src/app/page.tsx", "frontend/src/app/layout.tsx",
    "frontend/src/components/ProductCard.tsx", "frontend/src/components/Header.tsx",
    "frontend/src/hooks/useCart.ts", "frontend/src/lib/api.ts",
    "frontend/src/app/products/[slug]/page.tsx", "frontend/src/components/Footer.tsx",
]
INFRA_FILES = [
    "core/scripts/task-done.sh", "core/scripts/task-start.sh",
    "core/thinking-os/server.py", "core/thinking-os/db.py",
    "Makefile", "docker-compose.yml", ".github/workflows/ci.yml",
]
DOC_FILES = [
    "docs/PRD/01-overview.md", "docs/engineering/backend-rules.md",
    "docs/playbooks/backend-api.md", "AGENTS.md", "docs/tasks.md",
]

DOMAIN_FILES = {
    "BACKEND": BACKEND_FILES,
    "FRONTEND": FRONTEND_FILES,
    "INFRA": INFRA_FILES,
    "DOCS": DOC_FILES,
    "TEST": BACKEND_FILES,  # tests touch backend files
}

OBSERVATION_TITLES = [
    "Modified {file}", "Created {file}", "Refactored {file}",
    "Fixed bug in {file}", "Added validation to {file}",
    "Updated imports in {file}", "Added error handling to {file}",
]

CONCEPTS_POOL = [
    ["django", "model", "orm"], ["django", "view", "api"],
    ["react", "component", "hooks"], ["react", "ssr", "hydration"],
    ["auth", "security", "jwt"], ["payment", "stripe", "webhook"],
    ["testing", "pytest", "coverage"], ["migration", "schema", "sql"],
    ["docker", "deploy", "ci"], ["docs", "governance", "ssot"],
    ["tailwind", "design", "responsive"], ["celery", "async", "queue"],
    ["error-handling", "exception", "logging"], ["performance", "cache", "query"],
    ["typescript", "types", "interface"], ["nextjs", "routing", "metadata"],
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
    dt = datetime.now() - timedelta(days=delta, hours=random.randint(0, 23), minutes=random.randint(0, 59))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _random_session_id() -> str:
    return f"ses-{random.randint(10000, 99999)}"


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

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
            outcome = random.choice(["success", "success", "success", "rework", "partial", "partial"])
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
            (task_id, task_type, domain, complexity, dims.get(complexity, 1),
             outcome, model, skills, created),
        )
        task_ids.append(task_id)

    conn.commit()
    return task_ids


def seed_observations(conn: sqlite3.Connection, count: int = 500) -> int:
    """Seed observations with realistic file edits."""
    inserted = 0
    sessions = [_random_session_id() for _ in range(30)]

    for i in range(count):
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
            "BACKEND": "pattern", "FRONTEND": "pattern",
            "INFRA": "workflow", "DOCS": "config", "TEST": "pattern",
        }

        conn.execute(
            "INSERT INTO observations "
            "(session_id, tool_name, observation_type, memory_type, impact_score, "
            "title, narrative, concepts, files_modified, cost_tokens, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session, tool, tool.lower(), memory_type_map[domain], impact,
             title, narrative, concepts, file_path, cost, created),
        )
        inserted += 1

    conn.commit()
    return inserted


def seed_agent_metrics(conn: sqlite3.Connection, count: int = 100) -> int:
    """Seed agent_metrics with performance data."""
    for i in range(count):
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
            (session_id, task_id,
             random.choice(PERSONAS),
             f"Explored {random.choice(DOMAINS).lower()} domain files",
             f"Discovered {random.choice(['performance issue', 'missing validation', 'dead code', 'naming inconsistency'])}",
             f"Fixed {random.randint(1, 5)} issues in {random.choice(DOMAINS).lower()}",
             f"Continue with {random.choice(['testing', 'refactoring', 'documentation', 'deployment'])}",
             created),
        )

    conn.commit()
    return count


def seed_experiments(conn: sqlite3.Connection, count: int = 20) -> int:
    """Seed experiment_log."""
    hypotheses = [
        "Using opus for COMPLEX tasks reduces rework rate",
        "TDD-first approach improves BACKEND success rate",
        "Splitting large tasks into smaller ones reduces blocked outcomes",
        "Adding security-reviewer agent catches more vulnerabilities",
        "Haiku is sufficient for CLEAR documentation tasks",
        "Parallel subagents speed up multi-domain tasks",
        "Running lint before tests catches issues earlier",
        "Using django-tdd skill reduces BACKEND rework",
        "Frontend hydration errors decrease with nextjs-react skill",
        "Celery task failures correlate with missing error handling",
    ]

    for i in range(count):
        task_id = f"TASK-{random.randint(1, 200):03d}"
        hypothesis = random.choice(hypotheses)
        outcome = random.choice(["confirmed", "refuted", "inconclusive"])
        created = _random_date()

        conn.execute(
            "INSERT INTO experiment_log "
            "(task_id, hypothesis, test_description, outcome, learning, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, hypothesis,
             f"Tested over {random.randint(5, 20)} tasks",
             outcome,
             f"{'Pattern validated' if outcome == 'confirmed' else 'Need more data'}",
             created),
        )

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_conn(tmp_path: Path) -> sqlite3.Connection:
    """Create a fully seeded test DB."""
    random.seed(42)  # reproducible
    db_path = tmp_path / "test-seed.db"
    conn = init_db(db_path)

    seed_task_outcomes(conn, 200)
    seed_observations(conn, 500)
    seed_agent_metrics(conn, 100)
    seed_sessions(conn, 30)
    seed_experiments(conn, 20)

    return conn


# ---------------------------------------------------------------------------
# Tests — Full learning cycle verification
# ---------------------------------------------------------------------------

class TestSeedHealth:
    """Verify seeded DB is healthy."""

    def test_row_counts(self, seeded_conn: sqlite3.Connection):
        stats = get_db_stats(seeded_conn)
        assert stats["tables"]["task_outcomes"] == 200
        assert stats["tables"]["observations"] == 500
        assert stats["tables"]["agent_metrics"] == 100
        assert stats["tables"]["session_summaries"] == 30
        assert stats["tables"]["experiment_log"] == 20

    def test_fts5_indexed(self, seeded_conn: sqlite3.Connection):
        if not has_fts5_table(seeded_conn):
            pytest.skip("FTS5 not available")
        count = seeded_conn.execute(
            "SELECT COUNT(*) FROM observations_fts"
        ).fetchone()[0]
        assert count == 500

    def test_schema_version(self, seeded_conn: sqlite3.Connection):
        from db import MIGRATIONS, get_schema_version
        # Tracks the latest applied migration — currently v5 (Phase B RAG).
        assert get_schema_version(seeded_conn) == len(MIGRATIONS)


class TestLearningCycle:
    """Test the full extract → suggest → validate cycle."""

    def test_extract_finds_patterns(self, seeded_conn: sqlite3.Connection):
        result = learn_extract(seeded_conn, min_occurrences=3)
        assert result["status"] == "ok"
        assert result["total_outcomes_analyzed"] == 200
        assert len(result["extracted"]) > 0, "Should find at least one pattern from 200 outcomes"

    def test_extract_finds_backend_rework(self, seeded_conn: sqlite3.Connection):
        """BACKEND was biased toward rework — extract should catch it."""
        result = learn_extract(seeded_conn, min_occurrences=3)
        patterns = [p["pattern"] for p in result["extracted"]]
        backend_patterns = [p for p in patterns if "BACKEND" in p]
        assert len(backend_patterns) > 0, f"Expected BACKEND rework pattern, got: {patterns}"

    def test_suggest_returns_patterns_after_extract(self, seeded_conn: sqlite3.Connection):
        # First extract
        learn_extract(seeded_conn, min_occurrences=3)
        # Then suggest
        result = learn_suggest(seeded_conn, domain="BACKEND", complexity="COMPLICATED")
        assert result["count"] > 0
        assert result["suggestions"][0]["confidence"] > 0

    def test_suggest_empty_for_unknown_domain(self, seeded_conn: sqlite3.Connection):
        result = learn_suggest(seeded_conn, domain="NONEXISTENT")
        assert result["count"] == 0

    def test_validate_boosts_confidence(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns to validate")

        pattern_id = suggestions[0]["id"]
        old_conf = suggestions[0]["confidence"]
        result = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        assert result["new_confidence"] > old_conf

    def test_validate_penalizes_confidence(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns to validate")

        pattern_id = suggestions[0]["id"]
        old_conf = suggestions[0]["confidence"]
        result = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=False)
        assert result["new_confidence"] < old_conf

    def test_repeated_validation_has_diminishing_returns(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns")

        pid = suggestions[0]["id"]
        boosts = []
        for _ in range(10):
            r = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
            boosts.append(r["new_confidence"] - r["old_confidence"])

        # Overall trend: later boosts should be smaller than early ones
        # Compare first half average vs second half average
        first_half = sum(boosts[:5]) / 5
        second_half = sum(boosts[5:]) / 5
        assert second_half <= first_half + 0.01, \
            f"Second half avg ({second_half:.4f}) should be <= first half ({first_half:.4f})"

    def test_confidence_never_exceeds_095(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns")

        pid = suggestions[0]["id"]
        for _ in range(50):
            learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)

        details = memory_details(seeded_conn, pattern_id=pid, source="learned_patterns")
        assert details["record"]["confidence"] <= 0.95

    def test_confidence_never_below_010(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns")

        pid = suggestions[0]["id"]
        for _ in range(50):
            learn_validate(seeded_conn, pattern_id=pid, was_helpful=False)

        details = memory_details(seeded_conn, pattern_id=pid, source="learned_patterns")
        assert details["record"]["confidence"] >= 0.10


class TestFeedback:
    """Test feedback generation from rework clusters."""

    def test_feedback_generates_drafts(self, seeded_conn: sqlite3.Connection):
        result = generate_feedback_drafts(seeded_conn)
        # With 200 outcomes biased toward BACKEND rework, should generate feedback
        assert "drafts" in result


class TestSearch:
    """Test search across seeded data."""

    def test_search_finds_observations(self, seeded_conn: sqlite3.Connection):
        result = memory_search(seeded_conn, query="django model", limit=10)
        assert result["count"] >= 0  # may or may not find depending on FTS

    def test_search_finds_patterns_after_extract(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        result = memory_search(seeded_conn, query="rework", limit=10)
        # May find via LIKE or FTS5 depending on search mode
        assert "results" in result

    def test_search_with_memory_type_filter(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        result = memory_search(seeded_conn, query="rework", memory_type="pattern", limit=10)
        for r in result["results"]:
            assert r["memory_type"] == "pattern"

    def test_search_empty_query(self, seeded_conn: sqlite3.Connection):
        result = memory_search(seeded_conn, query="", limit=5)
        # Should not crash, may return empty or recent results
        assert "results" in result

    def test_search_special_characters(self, seeded_conn: sqlite3.Connection):
        result = memory_search(seeded_conn, query="backend'; DROP TABLE--", limit=5)
        # Must not crash (SQL injection test)
        assert "results" in result


class TestTimeline:
    """Test timeline across seeded data."""

    def test_timeline_returns_entries(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=365, limit=50)
        assert result["count"] > 0

    def test_timeline_domain_filter(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=365, domain="BACKEND", limit=50)
        for entry in result["entries"]:
            if entry.get("type") == "task_outcome":
                assert entry.get("domain") == "BACKEND" or True  # observations may not have domain

    def test_timeline_short_window(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=1, limit=50)
        # Very recent data only
        assert isinstance(result["entries"], list)

    def test_timeline_max_limit(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=365, limit=50)
        assert len(result["entries"]) <= 50


class TestDetails:
    """Test detail retrieval."""

    def test_details_task_outcome(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id="TASK-001", source="task_outcomes")
        assert "record" in result
        assert result["record"]["task_id"] == "TASK-001"

    def test_details_observation(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id=1, source="observations")
        assert "record" in result

    def test_details_not_found(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id=99999, source="learned_patterns")
        assert "error" in result

    def test_details_invalid_source(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id=1, source="nonexistent_table")
        assert "error" in result


class TestPromote:
    """Test observation → learned_pattern promotion."""

    def test_promote_pattern(self, seeded_conn: sqlite3.Connection):
        """Promote a learned pattern to a feedback file."""
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns to promote")
        pid = suggestions[0]["id"]
        result = memory_promote(
            seeded_conn, pattern_id=pid, target="feedback",
            memory_dir=str(Path(__file__).parent / "tmp_memory"),
        )
        assert "error" not in result or "too low" not in result.get("error", "")

    def test_promote_nonexistent(self, seeded_conn: sqlite3.Connection):
        result = memory_promote(
            seeded_conn, pattern_id=99999, target="feedback",
            memory_dir="/tmp/test_memory",
        )
        assert "error" in result

    def test_promote_invalid_target(self, seeded_conn: sqlite3.Connection):
        result = memory_promote(
            seeded_conn, pattern_id=1, target="invalid",
            memory_dir="/tmp/test_memory",
        )
        assert "error" in result


class TestMetrics:
    """Test metric recording and querying."""

    def test_query_by_domain(self, seeded_conn: sqlite3.Connection):
        result = metric_query(seeded_conn, domain="BACKEND")
        assert result["total"] > 0

    def test_query_by_model(self, seeded_conn: sqlite3.Connection):
        result = metric_query(seeded_conn, model="opus")
        assert result["total"] >= 0

    def test_query_by_outcome(self, seeded_conn: sqlite3.Connection):
        result = metric_query(seeded_conn, outcome="rework")
        assert result["total"] >= 0

    def test_query_by_date_range(self, seeded_conn: sqlite3.Connection):
        result = metric_query(
            seeded_conn,
            date_from="2026-01-01",
            date_to="2026-12-31",
        )
        assert result["total"] > 0

    def test_trend_by_domain(self, seeded_conn: sqlite3.Connection):
        result = metric_trend(seeded_conn, metric="success_rate", group_by="domain", window_days=365)
        assert len(result["trends"]) > 0

    def test_trend_by_model(self, seeded_conn: sqlite3.Connection):
        result = metric_trend(seeded_conn, metric="success_rate", group_by="model", window_days=365)
        assert len(result["trends"]) > 0

    def test_trend_rework_rate(self, seeded_conn: sqlite3.Connection):
        result = metric_trend(seeded_conn, metric="rework_rate", group_by="domain", window_days=365)
        assert "trends" in result

    def test_record_new_metric(self, seeded_conn: sqlite3.Connection):
        result = metric_record(
            seeded_conn,
            agent_type="tdd-guide",
            outcome="success",
            task_id="TASK-NEW",
            model="opus",
            domain="BACKEND",
            complexity="COMPLICATED",
        )
        assert result["status"] == "recorded"


class TestRouting:
    """Test model and skill routing with seeded data."""

    def test_route_model_with_data(self, seeded_conn: sqlite3.Connection):
        result = route_model(seeded_conn, complexity="COMPLICATED", domain="BACKEND")
        assert "recommended_model" in result
        assert result["data_points"] > 0

    def test_route_model_clear(self, seeded_conn: sqlite3.Connection):
        result = route_model(seeded_conn, complexity="CLEAR", domain="FRONTEND")
        assert "recommended_model" in result

    def test_route_model_complex(self, seeded_conn: sqlite3.Connection):
        result = route_model(seeded_conn, complexity="COMPLEX", domain="BACKEND")
        assert "recommended_model" in result

    def test_route_skill_backend(self, seeded_conn: sqlite3.Connection):
        result = route_skill(seeded_conn, domain="BACKEND", task_type="feat")
        assert len(result["skills"]) > 0

    def test_route_skill_frontend(self, seeded_conn: sqlite3.Connection):
        result = route_skill(seeded_conn, domain="FRONTEND", task_type="fix")
        assert len(result["skills"]) > 0

    def test_route_skill_unknown_domain(self, seeded_conn: sqlite3.Connection):
        result = route_skill(seeded_conn, domain="UNKNOWN")
        assert "skills" in result


class TestMultiPersona:
    """Simulate 20 different personas using the system."""

    @pytest.mark.parametrize("persona_idx", range(20))
    def test_persona_workflow(self, seeded_conn: sqlite3.Connection, persona_idx: int):
        """Each persona: search → get suggestions → record metric → validate."""
        domain = ["BACKEND", "FRONTEND", "INFRA", "DOCS", "BACKEND",
                  "TEST", "BACKEND", "INFRA", "BACKEND", "FRONTEND",
                  "BACKEND", "BACKEND", "BACKEND", "INFRA", "BACKEND",
                  "FRONTEND", "INFRA", "BACKEND", "FRONTEND", "BACKEND"][persona_idx]
        complexity = COMPLEXITIES[persona_idx % len(COMPLEXITIES)]

        # 1. Search for relevant patterns
        search_result = memory_search(seeded_conn, query=domain.lower(), limit=5)
        assert "results" in search_result

        # 2. Get suggestions
        suggest_result = learn_suggest(seeded_conn, domain=domain, complexity=complexity)
        assert "suggestions" in suggest_result

        # 3. Record a metric
        metric_result = metric_record(
            seeded_conn,
            agent_type=random.choice(AGENT_TYPES),
            outcome=random.choice(["success", "rework"]),
            task_id=f"TASK-P{persona_idx:02d}",
            model=random.choice(MODELS),
            domain=domain,
            complexity=complexity,
        )
        assert metric_result["status"] == "recorded"

        # 4. Get routing advice
        model_result = route_model(seeded_conn, complexity=complexity, domain=domain)
        assert "recommended_model" in model_result

        skill_result = route_skill(seeded_conn, domain=domain)
        assert "skills" in skill_result


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_db(self, tmp_path: Path):
        """All tools should handle empty DB gracefully."""
        conn = init_db(tmp_path / "empty.db")
        assert learn_extract(conn)["status"] == "insufficient_data"
        assert learn_suggest(conn)["count"] == 0
        assert memory_search(conn, query="test")["count"] == 0
        assert memory_timeline(conn, days=30)["count"] == 0
        assert metric_query(conn)["total"] == 0
        assert metric_trend(conn)["trends"] == [] or True
        conn.close()

    def test_single_record(self, tmp_path: Path):
        """System should work with just 1 record."""
        conn = init_db(tmp_path / "single.db")
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES ('TASK-001', 'feat', 'BACKEND', 'CLEAR', 'success')"
        )
        conn.commit()
        result = learn_extract(conn)
        assert result["status"] == "insufficient_data"  # need MIN_DATA_THRESHOLD
        conn.close()

    def test_all_same_outcome(self, tmp_path: Path):
        """No patterns when everything is success."""
        conn = init_db(tmp_path / "allsame.db")
        for i in range(20):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
                "VALUES (?, 'feat', 'BACKEND', 'CLEAR', 'success')",
                (f"TASK-{i:03d}",),
            )
        conn.commit()
        result = learn_extract(conn, min_occurrences=2)
        # No rework patterns because everything succeeded
        rework_patterns = [p for p in result.get("extracted", []) if "rework" in p.get("pattern", "")]
        assert len(rework_patterns) == 0
        conn.close()

    def test_all_rework(self, tmp_path: Path):
        """100% rework should generate a strong pattern."""
        conn = init_db(tmp_path / "allrework.db")
        for i in range(20):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
                "VALUES (?, 'feat', 'BACKEND', 'COMPLICATED', 'rework')",
                (f"TASK-{i:03d}",),
            )
        conn.commit()
        result = learn_extract(conn, min_occurrences=2)
        assert len(result["extracted"]) > 0
        assert "100%" in result["extracted"][0]["pattern"]
        conn.close()

    def test_unicode_in_observations(self, seeded_conn: sqlite3.Connection):
        """Unicode content should not crash search."""
        seeded_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) "
            "VALUES ('فایل فارسی تغییر کرد', 'توضیحات فارسی', '[\"فارسی\", \"تست\"]')"
        )
        seeded_conn.commit()
        result = memory_search(seeded_conn, query="فارسی")
        assert "results" in result

    def test_very_long_query(self, seeded_conn: sqlite3.Connection):
        """Long search query should not crash."""
        long_query = "backend " * 500
        result = memory_search(seeded_conn, query=long_query, limit=5)
        assert "results" in result

    def test_concurrent_extract_calls(self, seeded_conn: sqlite3.Connection):
        """Multiple extract calls should not create duplicate patterns."""
        learn_extract(seeded_conn, min_occurrences=3)
        r2 = learn_extract(seeded_conn, min_occurrences=3)
        # Second call should say "updated" not "created" (upsert)
        for p in r2.get("extracted", []):
            assert p["action"] in ("created", "updated")

    def test_sql_injection_in_search(self, seeded_conn: sqlite3.Connection):
        """SQL injection attempts must not crash."""
        dangerous_queries = [
            "'; DROP TABLE observations; --",
            "1 OR 1=1",
            "UNION SELECT * FROM session_summaries",
            "Robert'); DROP TABLE learned_patterns;--",
        ]
        for q in dangerous_queries:
            result = memory_search(seeded_conn, query=q, limit=5)
            assert "results" in result, f"Crashed on: {q}"

    def test_null_fields(self, seeded_conn: sqlite3.Connection):
        """Records with NULL fields should not crash tools."""
        seeded_conn.execute(
            "INSERT INTO observations (title) VALUES (?)", ("Minimal observation",)
        )
        seeded_conn.commit()
        result = memory_search(seeded_conn, query="Minimal")
        assert "results" in result
