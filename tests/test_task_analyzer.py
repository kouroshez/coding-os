"""
Phase N — Task Analyzer tests.

Validate signal extraction from representative prompts covering the full
axes: action verbs, domain keywords, urgency, external deps, scope from
dimensions, has-unknowns, breaking change lexical hints, production impact.

Spec: docs/phase-n-role-based-routing-plan.md §2.1
"""

from __future__ import annotations

import sys
from pathlib import Path

_THINKING_OS = Path(__file__).resolve().parent.parent / "src" / "core" / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from task_analyzer import analyze_task  # noqa: E402


def test_create_backend_api():
    sig = analyze_task("add pagination to /users API endpoint", complexity="COMPLICATED", dimensions=3)
    assert sig.action == "create"
    assert "backend" in sig.domain
    assert sig.scope_size == "small"
    assert sig.urgency == "normal"


def test_debug_incident():
    sig = analyze_task(
        "incident: production down, pager fired, fix the crash on /checkout",
        complexity="CHAOTIC", dimensions=1,
    )
    assert sig.action == "debug"
    assert sig.urgency == "incident"
    assert sig.has_production_impact is True


def test_research_spike():
    sig = analyze_task(
        "investigate alternatives to Redis for session storage, compare options",
        complexity="COMPLEX", dimensions=4,
    )
    assert sig.action == "research"
    assert sig.scope_size == "medium"


def test_external_dependency_stripe():
    sig = analyze_task(
        "integrate Stripe webhook for subscription renewal, needs api key",
        complexity="COMPLICATED", dimensions=3,
    )
    assert sig.external_dependency is True
    assert "backend" in sig.domain


def test_frontend_component():
    sig = analyze_task(
        "build a new React component for user profile page",
        complexity="COMPLICATED", dimensions=2,
    )
    assert sig.action == "create"
    assert "frontend" in sig.domain


def test_has_unknowns_signal():
    sig = analyze_task("not sure how to approach this, maybe use TBD", complexity="COMPLICATED", dimensions=2)
    assert sig.has_unknowns is True


def test_breaking_change_lexical():
    sig = analyze_task(
        "drop column email from users table, breaking change",
        complexity="COMPLICATED", dimensions=3,
    )
    assert sig.breaking_change is True
    assert "db" in sig.domain


def test_large_scope_from_dimensions():
    sig = analyze_task("create order service", complexity="COMPLEX", dimensions=7)
    assert sig.scope_size == "large"


def test_recursive_scope_from_dimensions():
    sig = analyze_task("create monolith-splitting migration", complexity="COMPLEX", dimensions=9)
    assert sig.scope_size == "recursive"


def test_no_mcp_still_returns_valid_signals():
    """Without MCP hooks, analyzer still returns a valid TaskSignals."""
    sig = analyze_task("refactor the auth module", complexity="COMPLICATED", dimensions=4)
    assert sig.action == "refactor"
    # Novelty defaults to 0.5 when no cos_search hook available
    assert sig.novelty == 0.5
    assert sig.source_errors == [] or all("budget_overrun" in e for e in sig.source_errors)


def test_extraction_budget_met():
    """Extraction must complete under the 500ms budget."""
    sig = analyze_task("add pagination to /users", complexity="COMPLICATED", dimensions=3)
    assert sig.extraction_ms < 500, f"extraction took {sig.extraction_ms}ms (budget 500ms)"


def test_audit_action_detected():
    sig = analyze_task("security audit of the OAuth flow", complexity="COMPLEX", dimensions=5)
    assert sig.action == "audit"
    assert "security" in sig.domain or "auth" in sig.domain


def test_deploy_action_detected():
    sig = analyze_task("ship the v2 release to production", complexity="COMPLICATED", dimensions=3)
    assert sig.action == "deploy"


def test_document_action_detected():
    sig = analyze_task("write docs / ADR for the new auth flow", complexity="COMPLICATED", dimensions=2)
    assert sig.action == "document"
    assert "docs" in sig.domain
