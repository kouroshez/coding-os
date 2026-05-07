"""
Phase N — End-to-end scenario tests.

Verify the full pipeline: prompt → analyze_task → compose_chain produces
the correct formula chain across 10+ realistic scenarios spanning every
preset, every situation override, and key composer paths.

Spec: docs/phase-n-role-based-routing-plan.md §5.1 · flowchart V1
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THINKING_OS = Path(__file__).resolve().parent.parent / "core" / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from formula_composer import compose_chain, reset_registry_cache  # noqa: E402
from task_analyzer import analyze_task  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_cache()
    yield
    reset_registry_cache()


# ---------------------------------------------------------------------------
# Scenario matrix — each entry is (name, prompt, complexity, dims, situation,
# expected_source, expected_chain_prefix, must_include_role_ids).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", [
    # Greenfield backend
    {
        "name": "greenfield-backend-api",
        "prompt": "add a new /orders POST endpoint with pagination to the backend API",
        "complexity": "COMPLICATED",
        "dimensions": 4,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "greenfield-backend-api",
        "must_include": ["analyst", "implementer", "reviewer"],
    },
    # Schema migration with breaking change
    {
        "name": "schema-migration",
        "prompt": "drop column email from users table, breaking change required",
        "complexity": "COMPLICATED",
        "dimensions": 3,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "schema-migration",
        "must_include": ["analyst", "architect", "security_auditor", "implementer", "reviewer"],
    },
    # External integration (Stripe)
    {
        "name": "external-integration-stripe",
        "prompt": "integrate Stripe webhook for subscription renewal, needs api key setup",
        "complexity": "COMPLICATED",
        "dimensions": 3,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "external-integration",
        "must_include": ["researcher", "analyst", "architect", "implementer", "reviewer", "security_auditor"],
    },
    # Frontend feature
    {
        "name": "frontend-feature",
        "prompt": "build a new React component for the user profile page",
        "complexity": "COMPLICATED",
        "dimensions": 2,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "greenfield-frontend-feature",
        "must_include": ["analyst", "implementer", "reviewer"],
    },
    # Debug standard (non-incident)
    {
        "name": "debug-standard",
        "prompt": "fix the crash in the checkout flow, users seeing 500 errors",
        "complexity": "COMPLICATED",
        "dimensions": 3,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "debug-standard",
        "must_include": ["debugger", "reviewer"],
    },
    # Docs-only
    {
        "name": "docs-only",
        "prompt": "document the new auth flow in docs, write an ADR",
        "complexity": "COMPLICATED",
        "dimensions": 2,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "docs-only-update",
        "must_include": ["documenter"],
    },
    # Security audit full
    {
        "name": "security-audit",
        "prompt": "security audit of the OAuth flow, vet all auth boundaries",
        "complexity": "COMPLEX",
        "dimensions": 5,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "security-audit-full",
        "must_include": ["security_auditor"],
    },
    # Research spike
    {
        "name": "research-spike",
        "prompt": "investigate alternatives to Redis, compare options, evaluate tradeoffs",
        "complexity": "COMPLEX",
        "dimensions": 4,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "research-spike",
        "must_include": ["researcher"],
    },
    # Refactor sprint
    {
        "name": "refactor-sprint",
        "prompt": "refactor the auth module, consolidate the JWT and session handling",
        "complexity": "COMPLICATED",
        "dimensions": 3,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "refactor-sprint",
        "must_include": ["refactorer", "architect", "implementer", "reviewer"],
    },
    # Deploy release
    {
        "name": "deploy-release",
        "prompt": "ship the v2 release to production, finalize the rollout",
        "complexity": "COMPLICATED",
        "dimensions": 3,
        "situation": None,
        "expected_source": "preset",
        "expected_preset_id": "deploy-release",
        "must_include": ["security_auditor", "deployer", "observer"],
    },
    # Incident override (situation wins even if preset would match)
    {
        "name": "incident-override",
        "prompt": "add a new /orders endpoint to the backend",
        "complexity": "COMPLICATED",
        "dimensions": 3,
        "situation": "incident-response",
        "expected_source": "situation",
        "expected_preset_id": None,
        "must_include": ["debugger", "reviewer"],
    },
    # Legacy takeover (via situation)
    {
        "name": "legacy-takeover-situation",
        "prompt": "get oriented in the inherited codebase, no docs anywhere",
        "complexity": "COMPLEX",
        "dimensions": 5,
        "situation": "existing-project-takeover",
        "expected_source": "situation",
        "expected_preset_id": None,
        "must_include": ["analyst"],
    },
])
def test_e2e_scenario(scenario):
    """Run the full analyze→compose pipeline and assert the chain is correct."""
    signals = analyze_task(
        prompt=scenario["prompt"],
        complexity=scenario["complexity"],
        dimensions=scenario["dimensions"],
    )

    chain = compose_chain(
        signals,
        situation_id=scenario["situation"],
    )

    # Source of chain must match expected (preset / composer / situation / fallback)
    assert chain.source == scenario["expected_source"], (
        f"[{scenario['name']}] expected source={scenario['expected_source']} "
        f"got {chain.source} (reason: {chain.reason})"
    )

    # If preset expected, verify id
    if scenario["expected_preset_id"]:
        assert chain.preset_id == scenario["expected_preset_id"], (
            f"[{scenario['name']}] expected preset={scenario['expected_preset_id']} "
            f"got {chain.preset_id}"
        )
        # Preset version must be stamped (N.5-C)
        assert chain.preset_version is not None and len(chain.preset_version) == 16

    # All required roles must appear in the chain
    for role in scenario["must_include"]:
        assert role in chain.chain, (
            f"[{scenario['name']}] role {role} missing from chain={chain.chain}"
        )

    # Effective threshold must always be stamped
    assert chain.effective_threshold is not None
    assert 0 <= chain.effective_threshold <= 15


# ---------------------------------------------------------------------------
# Latency budget (N.5 enterprise requirement)
# ---------------------------------------------------------------------------

def test_analyze_compose_under_latency_budget():
    """End-to-end analyze + compose under 600ms (500ms analyzer + 100ms composer)."""
    import time
    t0 = time.time()
    signals = analyze_task(
        prompt="add Stripe webhook integration for payment processing",
        complexity="COMPLICATED",
        dimensions=4,
    )
    chain = compose_chain(signals)
    elapsed_ms = int((time.time() - t0) * 1000)
    assert elapsed_ms < 600, (
        f"e2e pipeline took {elapsed_ms}ms (budget 600ms, analyzer={signals.extraction_ms}ms)"
    )
    assert len(chain.chain) > 0


# ---------------------------------------------------------------------------
# Determinism under concurrent load (thread-safety smoke)
# ---------------------------------------------------------------------------

def test_compose_deterministic_under_threading():
    """Same signals produce identical chains across threads (immutable cache)."""
    import threading

    signals = analyze_task(
        prompt="add new API endpoint for orders",
        complexity="COMPLICATED",
        dimensions=4,
    )
    results: list = []
    lock = threading.Lock()

    def worker():
        chain = compose_chain(signals)
        with lock:
            results.append((chain.source, tuple(chain.chain), chain.preset_id))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    first = results[0]
    for r in results[1:]:
        assert r == first, f"concurrent composer produced inconsistent chains: {first} vs {r}"


# ---------------------------------------------------------------------------
# Fallback behavior (never empty chain)
# ---------------------------------------------------------------------------

def test_empty_signals_returns_fallback_not_empty():
    """Completely empty prompt must still yield a valid non-empty chain."""
    signals = analyze_task(prompt="", complexity="COMPLICATED", dimensions=1)
    chain = compose_chain(signals, preset_min_score=15)  # force past all presets
    assert len(chain.chain) >= 1
    # Acceptable sources: composer (if scoring succeeded despite empty prompt)
    # or fallback (if no role scored high enough)
    assert chain.source in ("composer", "fallback")


def test_connection_pool_multithreaded_safe():
    """N.5-A: thread-local connection pool must survive concurrent gets."""
    sys.path.insert(0, str(_THINKING_OS))
    from database import close_pool, get_pooled_conn, pool_stats

    import threading
    close_pool()

    errors: list[Exception] = []

    def worker():
        try:
            conn = get_pooled_conn()
            conn.execute("SELECT 1").fetchone()
            # Second call in same thread should hit the pool cache
            conn2 = get_pooled_conn()
            assert conn is conn2
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"connection pool errors under load: {errors}"
    stats = pool_stats()
    # 20 threads × at least 1 miss each = ≥1 miss; many hits from reuse
    assert stats["misses"] >= 1
