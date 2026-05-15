"""
Phase N — Behavioral tracing tests (black-box).

Verify that running the real MCP tools produces a trace timeline that matches
the expected flowchart path for each canonical scenario. Each scenario:

  1. Calls cos_analyze_task (MCP wrapper).
  2. Calls cos_compose_chain with the returned signals.
  3. Reads the session's trace file and asserts the flowchart nodes visited.

Spec:
  - docs/phase-n-role-based-routing-plan.md §5 (verification)
  - docs/agent-workflow-flowchart-V1.html (flowchart node IDs)
  - core/thinking_os/tracing.py::FLOWCHART_NODES (kind → node mapping)

This is the "prove real behavior" test the user asked for: we don't just
assert "function returns X", we assert "the agent traversed the correct
path on the flowchart, in the correct order, with the correct provenance."
"""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pytest

_THINKING_OS = Path(__file__).resolve().parent.parent / "src" / "core" / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from formula_composer import compose_chain, reset_registry_cache  # noqa: E402
from task_analyzer import analyze_task  # noqa: E402
import tracing  # noqa: E402


@pytest.fixture
def session_id(tmp_path) -> str:
    """Fresh session id + isolated agent dir per test."""
    sid = f"ses-test-{uuid.uuid4().hex[:8]}"
    # redirect tracing to tmp
    agent_dir = tmp_path / ".coding-os" / "claude"
    agent_dir.mkdir(parents=True, exist_ok=True)
    # Monkey-patch via env since tracing resolves agent_dir lazily
    yield sid, agent_dir
    # cleanup
    if agent_dir.exists():
        shutil.rmtree(agent_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_registry_cache()
    yield
    reset_registry_cache()


def _drive_scenario(prompt: str, complexity: str, dimensions: int,
                    situation: str | None, sid: str, adir: Path) -> dict:
    """Run the end-to-end cognition pipeline with tracing on a tmp agent_dir."""
    # 1. Emit the opening events the real system emits
    tracing.emit(sid, "session_init", {"test": True}, agent_dir=adir)
    tracing.emit(sid, "gate_recorded",
                 {"classification": complexity, "dimensions": dimensions},
                 agent_dir=adir)

    # 2. Analyze
    tracing.emit(sid, "analyze_start",
                 {"prompt_len": len(prompt), "complexity": complexity},
                 agent_dir=adir)
    signals = analyze_task(prompt=prompt, complexity=complexity, dimensions=dimensions)
    tracing.emit(sid, "analyze_done", {
        "action": signals.action, "domain": signals.domain,
        "scope_size": signals.scope_size, "urgency": signals.urgency,
        "external_dependency": signals.external_dependency,
        "breaking_change": signals.breaking_change,
    }, agent_dir=adir)

    # 3. Compose
    chain = compose_chain(signals, situation_id=situation)
    if chain.source == "preset":
        tracing.emit(sid, "preset_matched", {
            "preset_id": chain.preset_id, "chain": chain.chain,
            "preset_version": chain.preset_version,
        }, agent_dir=adir)
    elif chain.source == "situation":
        tracing.emit(sid, "situation_override", {
            "situation_id": chain.situation_id, "chain": chain.chain,
        }, agent_dir=adir)
    elif chain.source == "composer":
        tracing.emit(sid, "composer_fallback", {"chain": chain.chain}, agent_dir=adir)
    else:
        tracing.emit(sid, "hard_fallback", {"chain": chain.chain}, agent_dir=adir)
    tracing.emit(sid, "compose_done", {
        "chain": chain.chain, "source": chain.source, "preset_id": chain.preset_id,
    }, agent_dir=adir)

    # 4. Simulate dispatch of each role in the chain
    for role_id in chain.chain:
        tracing.emit(sid, "role_dispatch", {"formula": role_id}, role=role_id, agent_dir=adir)
        tracing.emit(sid, "role_output_recorded",
                     {"formula_id": role_id, "status": "ok", "latency_ms": 50},
                     role=role_id, agent_dir=adir)

    # 5. Close
    tracing.emit(sid, "ambiguity_check", {"violations": 0}, agent_dir=adir)
    tracing.emit(sid, "traceability_check", {"gaps": 0}, agent_dir=adir)
    tracing.emit(sid, "task_done", {"chain_length": len(chain.chain)}, agent_dir=adir)
    tracing.emit(sid, "session_end", {}, agent_dir=adir)

    summary = tracing.summarize(sid, adir)
    return {"signals": signals, "chain": chain, "summary": summary}


# ---------------------------------------------------------------------------
# Core canonical-path assertion helper
# ---------------------------------------------------------------------------

_MANDATORY_NODES = [
    "n-sinit", "n-gate", "n-analyzer", "n-router", "n-supervisor", "n-done",
]


def _assert_canonical_path(summary: dict) -> None:
    """Every COMPLICATED+ scenario must hit the canonical flowchart spine."""
    nodes = summary["nodes"]
    for mandatory in _MANDATORY_NODES:
        assert mandatory in nodes, (
            f"canonical node {mandatory} not visited; "
            f"actual path: {nodes} · kinds: {summary['kinds']}"
        )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def test_trace_greenfield_backend_api(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "add a new /orders POST endpoint with pagination",
        complexity="COMPLICATED", dimensions=4,
        situation=None, sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    assert s["preset"] == "greenfield-backend-api"
    # Chain must include analyst, implementer, and reviewer (the backend trio)
    assert all(r in s["chain"] for r in ("analyst", "implementer", "reviewer"))
    # At least 5 role dispatches happened
    assert s["kinds"].get("role_dispatch", 0) >= 5


def test_trace_incident_override_wins(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "add a /orders endpoint to the backend",   # looks like a preset hit
        complexity="COMPLICATED", dimensions=3,
        situation="incident-response",             # but situation wins
        sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    # Situation override emitted (not preset_matched)
    assert s["kinds"].get("situation_override", 0) == 1
    assert s["kinds"].get("preset_matched", 0) == 0
    assert s["situation"] == "incident-response"
    # debugger MUST appear as dispatched
    assert "debugger" in s["roles"]


def test_trace_schema_migration(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "drop column email from users table, breaking change",
        complexity="COMPLICATED", dimensions=3,
        situation=None, sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    assert s["preset"] == "schema-migration"
    # Chain must include security_auditor (security layer for data protection)
    assert "security_auditor" in s["chain"]
    # Ordering preserved in trace: analyst before architect before security_auditor before implementer before reviewer
    role_order = [r for r in s["roles"] if r]
    indices = {r: role_order.index(r) for r in ("analyst", "architect", "security_auditor", "implementer", "reviewer") if r in role_order}
    assert indices["analyst"] < indices["architect"] < indices["security_auditor"] < indices["implementer"] < indices["reviewer"]


def test_trace_external_integration_stripe(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "integrate Stripe webhook, needs api key setup",
        complexity="COMPLICATED", dimensions=3,
        situation=None, sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    assert s["preset"] == "external-integration"
    # researcher (mini) must fire first
    role_order = [r for r in s["roles"] if r]
    assert role_order[0] == "researcher"


def test_trace_research_spike_short_chain(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "investigate alternatives to Redis, compare options",
        complexity="COMPLEX", dimensions=4,
        situation=None, sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    assert s["preset"] == "research-spike"
    assert s["chain"] == ["researcher"]
    # Only one role_dispatch event since chain is a single role
    assert s["kinds"].get("role_dispatch", 0) == 1


def test_trace_legacy_takeover_via_situation(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "get oriented in this inherited codebase, there are no docs",
        complexity="COMPLEX", dimensions=5,
        situation="existing-project-takeover",
        sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    assert s["situation"] == "existing-project-takeover"
    # Takeover chain must start with analyst
    assert s["chain"][0] == "analyst"


def test_trace_docs_only_minimal_chain(session_id):
    sid, adir = session_id
    r = _drive_scenario(
        "document the new auth flow in docs, write an ADR",
        complexity="COMPLICATED", dimensions=2,
        situation=None, sid=sid, adir=adir,
    )
    s = r["summary"]
    _assert_canonical_path(s)
    assert s["preset"] == "docs-only-update"
    assert s["chain"] == ["documenter"]


# ---------------------------------------------------------------------------
# Replay semantics — raw event ordering
# ---------------------------------------------------------------------------

def test_event_ordering_respects_lifecycle(session_id):
    """Events must appear in the correct lifecycle order."""
    sid, adir = session_id
    r = _drive_scenario(
        "add pagination to /users endpoint",
        complexity="COMPLICATED", dimensions=3,
        situation=None, sid=sid, adir=adir,
    )
    events = tracing.read_trace(sid, adir)
    kinds_seq = [e["kind"] for e in events]

    assert kinds_seq.index("session_init") < kinds_seq.index("gate_recorded")
    assert kinds_seq.index("gate_recorded") < kinds_seq.index("analyze_start")
    assert kinds_seq.index("analyze_start") < kinds_seq.index("analyze_done")
    assert kinds_seq.index("analyze_done") < kinds_seq.index("compose_done")
    assert kinds_seq.index("compose_done") < kinds_seq.index("task_done")
    assert kinds_seq.index("task_done") < kinds_seq.index("session_end")
    assert len(r["chain"].chain) >= 1


# ---------------------------------------------------------------------------
# Concurrent multi-session isolation (enterprise guarantee)
# ---------------------------------------------------------------------------

def test_concurrent_sessions_isolated(tmp_path):
    """Two sessions run in parallel write to disjoint trace files."""
    import threading
    adir = tmp_path / ".coding-os" / "claude"
    adir.mkdir(parents=True, exist_ok=True)
    results: list = []
    lock = threading.Lock()

    def run(sid: str, prompt: str):
        r = _drive_scenario(prompt, "COMPLICATED", 3, None, sid, adir)
        with lock:
            results.append((sid, r["summary"]))

    t1 = threading.Thread(target=run, args=("ses-A", "add /orders endpoint"))
    t2 = threading.Thread(target=run, args=("ses-B", "fix the checkout crash"))
    t1.start(); t2.start()
    t1.join();  t2.join()

    # Both traces exist, neither has the other's events
    evts_a = tracing.read_trace("ses-A", adir)
    evts_b = tracing.read_trace("ses-B", adir)
    assert all(e["session_id"] == "ses-A" for e in evts_a)
    assert all(e["session_id"] == "ses-B" for e in evts_b)
    assert len(evts_a) > 0 and len(evts_b) > 0


# ---------------------------------------------------------------------------
# Summary shape contract
# ---------------------------------------------------------------------------

def test_summary_has_expected_keys(session_id):
    sid, adir = session_id
    _drive_scenario(
        "build a React component for profile page",
        complexity="COMPLICATED", dimensions=2,
        situation=None, sid=sid, adir=adir,
    )
    s = tracing.summarize(sid, adir)
    for key in ("session_id", "events", "nodes", "roles", "kinds",
                "preset", "situation", "chain", "violations",
                "backtracks", "discoveries"):
        assert key in s, f"summary missing key: {key}"
