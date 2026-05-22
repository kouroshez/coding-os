"""Coding OS — Cognitive agent IO contracts (Phase M)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Anti-Ambiguity Criteria (7 canonical)
# ---------------------------------------------------------------------------


class AmbiguityCriterion(str, Enum):
    OBSERVABLE = "observable"
    MEASURABLE = "measurable"
    TESTABLE = "testable"
    SCOPED = "scoped"
    OWNED = "owned"
    REVERSIBLE_OR_JUSTIFIED = "reversible_or_justified"
    CONNECTED_TO_USER_VALUE = "connected_to_user_value"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class Metric(BaseModel):
    name: str
    target: str
    measurement: str


class Actor(BaseModel):
    id: str
    role: str
    capabilities: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    given: str
    when: str
    then: str


class GoalNode(BaseModel):
    id: str
    description: str
    children: list[GoalNode] = Field(default_factory=list)


GoalNode.model_rebuild()


class DecisionTable(BaseModel):
    conditions: list[str]
    actions: list[str]
    rules: list[dict[str, Any]] = Field(default_factory=list)


class ConceptualModel(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class StateMachine(BaseModel):
    entity: str
    states: list[str]
    transitions: list[dict[str, Any]] = Field(default_factory=list)


class EventDef(BaseModel):
    name: str
    trigger: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PermissionMatrix(BaseModel):
    actors: list[str]
    resources: list[str]
    rules: list[dict[str, Any]] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    nodes: list[str]
    edges: list[dict[str, str]] = Field(default_factory=list)


class Unknown(BaseModel):
    id: str
    description: str
    impact: str
    resolution: str = ""


class ADR(BaseModel):
    id: str
    title: str
    status: Literal["proposed", "accepted", "deprecated", "superseded"] = "proposed"
    context: str
    decision: str
    consequences: str
    alternatives: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    id: str
    formula: str
    given: str
    when: str
    then: str
    layer: str = ""


class SecurityFinding(BaseModel):
    id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    layer: str
    description: str
    remediation: str


class DeployStep(BaseModel):
    order: int
    action: str
    rollback: str = ""
    timeout_s: int = 60


class MonitorAlert(BaseModel):
    name: str
    condition: str
    severity: str
    runbook: str = ""


class RefactorItem(BaseModel):
    id: str
    location: str
    pattern: str
    description: str
    priority: Literal["high", "medium", "low"] = "medium"


# ---------------------------------------------------------------------------
# Formula-role input/output contracts (researcher..refactorer)
# ---------------------------------------------------------------------------


class ResearcherInput(BaseModel):
    task_description: str
    domain: str = ""
    scope_hint: str = ""


class ResearcherOutput(BaseModel):
    summary: str
    sources: list[dict[str, str]] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_next: str = ""


class AnalystInput(BaseModel):
    task_description: str
    researcher: ResearcherOutput | None = None
    intensity_steps: list[int] = Field(default_factory=lambda: list(range(1, 13)))


class AnalystOutput(BaseModel):
    problem_statement: str
    scope_in: list[str] = Field(default_factory=list)
    scope_out: list[str] = Field(default_factory=list)
    success_metrics: list[Metric] = Field(default_factory=list)
    actors: list[Actor] = Field(default_factory=list)
    goal_tree: GoalNode | None = None
    scenarios: list[Scenario] = Field(default_factory=list)
    decision_table: DecisionTable | None = None
    data_model: ConceptualModel | None = None
    state_machines: list[StateMachine] = Field(default_factory=list)
    events: list[EventDef] = Field(default_factory=list)
    permissions: PermissionMatrix | None = None
    dependencies: DependencyGraph | None = None
    unknowns: list[Unknown] = Field(default_factory=list)


class ArchitectInput(BaseModel):
    task_description: str
    researcher: ResearcherOutput | None = None
    analyst: AnalystOutput | None = None


class ArchitectOutput(BaseModel):
    selected_style: str
    adrs: list[ADR] = Field(default_factory=list)
    component_diagram: str = ""
    api_contracts: list[dict[str, Any]] = Field(default_factory=list)
    data_contracts: list[dict[str, Any]] = Field(default_factory=list)
    deployment_topology: dict[str, Any] = Field(default_factory=dict)
    nfr_targets: list[dict[str, Any]] = Field(default_factory=list)
    security_boundaries: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class DocumenterInput(BaseModel):
    task_description: str
    analyst: AnalystOutput | None = None
    architect: ArchitectOutput | None = None


class DocumenterOutput(BaseModel):
    docs_created: list[str] = Field(default_factory=list)
    docs_updated: list[str] = Field(default_factory=list)
    changelog_entry: str = ""
    readme_sections: list[str] = Field(default_factory=list)


class ImplementerInput(BaseModel):
    task_description: str
    analyst: AnalystOutput | None = None
    architect: ArchitectOutput | None = None
    intensity_steps: list[int] = Field(default_factory=lambda: list(range(1, 9)))


class ImplementerOutput(BaseModel):
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    implementation_notes: str = ""
    open_items: list[str] = Field(default_factory=list)


class ReviewerInput(BaseModel):
    task_description: str
    analyst: AnalystOutput | None = None
    implementer: ImplementerOutput | None = None


class ReviewerOutput(BaseModel):
    test_cases: list[TestCase] = Field(default_factory=list)
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
    review_findings: list[dict[str, Any]] = Field(default_factory=list)
    performance_results: dict[str, Any] = Field(default_factory=dict)
    passed: bool = True


class DebuggerInput(BaseModel):
    task_description: str
    error_description: str
    analyst: AnalystOutput | None = None


class DebuggerOutput(BaseModel):
    root_cause: str
    fault_chain: list[str] = Field(default_factory=list)
    fix_applied: str = ""
    regression_tests_added: list[str] = Field(default_factory=list)
    prevention_recommendation: str = ""


class SecurityAuditorInput(BaseModel):
    task_description: str
    analyst: AnalystOutput | None = None
    architect: ArchitectOutput | None = None
    scope: Literal["pre_design", "pre_release", "audit"] = "pre_release"


class SecurityAuditorOutput(BaseModel):
    findings: list[SecurityFinding] = Field(default_factory=list)
    auth_coverage: dict[str, Any] = Field(default_factory=dict)
    dependency_risks: list[dict[str, Any]] = Field(default_factory=list)
    secrets_audit: dict[str, Any] = Field(default_factory=dict)
    passed: bool = True


class DeployerInput(BaseModel):
    task_description: str
    implementer: ImplementerOutput | None = None
    reviewer: ReviewerOutput | None = None
    security_auditor: SecurityAuditorOutput | None = None


class DeployerOutput(BaseModel):
    deploy_steps: list[DeployStep] = Field(default_factory=list)
    rollback_steps: list[DeployStep] = Field(default_factory=list)
    feature_flags: list[str] = Field(default_factory=list)
    release_notes: str = ""
    deployed: bool = False


class ObserverInput(BaseModel):
    task_description: str
    deployer: DeployerOutput | None = None


class ObserverOutput(BaseModel):
    alerts_added: list[MonitorAlert] = Field(default_factory=list)
    dashboards_updated: list[str] = Field(default_factory=list)
    runbooks_created: list[str] = Field(default_factory=list)
    slo_targets: list[dict[str, Any]] = Field(default_factory=list)


class RefactorerInput(BaseModel):
    task_description: str
    scope: Literal["scout", "targeted", "full"] = "targeted"


class RefactorerOutput(BaseModel):
    items: list[RefactorItem] = Field(default_factory=list)
    debt_score_before: float = 0.0
    debt_score_after: float = 0.0
    files_changed: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Backtrack and Discovery events
# ---------------------------------------------------------------------------


class BacktrackEvent(BaseModel):
    from_formula: str
    to_formula: str
    reason: str
    ts: str = ""


class Discovery(BaseModel):
    kind: str
    summary: str
    impact_assessment: str
    decision: Literal["backtrack_now", "record_for_later"]
    ts: str = ""


# ---------------------------------------------------------------------------
# ExhaustiveEvidence — mandatory for tasks where intent.exhaustive=true
# ---------------------------------------------------------------------------
#
# Captures the audit-shaped evidence record required by the completion
# guardian when the user's prompt triggered the intent detector with
# exhaustive scope. The 6 predicates from intent-vocabulary.md
# (coverage_100, iterate_until_zero_residual, all_categories_evidence,
# exhaustive_grep, per_item_evidence, strict_zero_residual) are
# evaluated against the fields below by validate_exhaustive_evidence().


class ExhaustiveEvidence(BaseModel):
    categories_declared: list[str] = Field(default_factory=list)
    categories_covered: list[str] = Field(default_factory=list)
    counts_before: dict[str, int] = Field(default_factory=dict)
    counts_after: dict[str, int] = Field(default_factory=dict)
    files_searched: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    gaps_remaining: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reviewer_check: Literal["pending", "pass", "fail"] = "pending"
    audit_artifact_path: str | None = None


def validate_exhaustive_evidence(
    evidence: ExhaustiveEvidence | None,
    intent_predicates: list[str],
) -> list[str]:
    """Return the list of gap reasons; empty list = predicates satisfied.

    Used by the completion guardian (Stop hook) to decide whether a
    "done" claim has the evidence to back it up. Empty intent_predicates
    short-circuits to no gaps — non-exhaustive tasks have no obligation
    to populate this bundle.
    """
    if not intent_predicates:
        return []
    if evidence is None:
        return ["no_exhaustive_evidence_submitted"]

    gaps: list[str] = []
    declared = set(evidence.categories_declared)
    covered = set(evidence.categories_covered)

    if "coverage_100" in intent_predicates:
        missing = declared - covered
        if not declared:
            gaps.append("coverage_100: no categories declared")
        elif missing:
            gaps.append(f"coverage_100: missing categories {sorted(missing)}")

    if (
        "iterate_until_zero_residual" in intent_predicates
        or "strict_zero_residual" in intent_predicates
    ):
        residuals = {cat: count for cat, count in evidence.counts_after.items() if count > 0}
        if residuals:
            gaps.append(f"strict_zero_residual: residual hits {residuals}")
        for cat in declared:
            if cat not in evidence.counts_after:
                gaps.append(f"strict_zero_residual: no counts_after for {cat}")

    if "all_categories_evidence" in intent_predicates:
        if not covered:
            gaps.append("all_categories_evidence: no categories covered")
        for cat in covered:
            if cat not in evidence.counts_before:
                gaps.append(f"all_categories_evidence: no counts_before for {cat}")

    if "exhaustive_grep" in intent_predicates and not evidence.files_searched:
        gaps.append("exhaustive_grep: files_searched is empty")

    if "per_item_evidence" in intent_predicates:
        if not covered:
            gaps.append("per_item_evidence: no categories covered")

    if evidence.gaps_remaining:
        gaps.append(f"self_reported_gaps: {evidence.gaps_remaining}")

    if evidence.reviewer_check == "fail":
        gaps.append("reviewer_check: failed")
    elif evidence.reviewer_check == "pending":
        gaps.append("reviewer_check: pending — auto-reviewer not yet run")

    return gaps


# ---------------------------------------------------------------------------
# EvidenceBundle — immutable accumulator per session
# ---------------------------------------------------------------------------


class EvidenceBundle(BaseModel):
    task_marker: str
    persona_id: str
    intensity: Literal["light", "standard", "full"] = "standard"
    situation_id: str | None = None
    researcher: ResearcherOutput | None = None
    analyst: AnalystOutput | None = None
    architect: ArchitectOutput | None = None
    documenter: DocumenterOutput | None = None
    implementer: ImplementerOutput | None = None
    reviewer: ReviewerOutput | None = None
    debugger: DebuggerOutput | None = None
    security_auditor: SecurityAuditorOutput | None = None
    deployer: DeployerOutput | None = None
    observer: ObserverOutput | None = None
    refactorer: RefactorerOutput | None = None
    backtracks: list[BacktrackEvent] = Field(default_factory=list)
    discoveries: list[Discovery] = Field(default_factory=list)
    degraded_formulas: list[str] = Field(default_factory=list)
    exhaustive_evidence: ExhaustiveEvidence | None = None


# ---------------------------------------------------------------------------
# Bundle-field registry — single source of truth (Rule 1)
# ---------------------------------------------------------------------------
#
# Adding a new role still requires a Pydantic Output class above and a
# matching field on EvidenceBundle (compile-time Python typing constraint).
# This registry centralizes the role_id → output_class mapping so callers
# (cognition.py tools, dispatcher persistence, traceability gate) read
# from one place instead of duplicating the dict literal.

ROLE_OUTPUT_CLASSES: dict[str, type[BaseModel]] = {
    "researcher": ResearcherOutput,
    "analyst": AnalystOutput,
    "architect": ArchitectOutput,
    "documenter": DocumenterOutput,
    "implementer": ImplementerOutput,
    "reviewer": ReviewerOutput,
    "debugger": DebuggerOutput,
    "security_auditor": SecurityAuditorOutput,
    "deployer": DeployerOutput,
    "observer": ObserverOutput,
    "refactorer": RefactorerOutput,
}


def output_class_for(role_id: str) -> type[BaseModel] | None:
    """Pydantic Output class for a role id. None when unknown."""
    return ROLE_OUTPUT_CLASSES.get(role_id)


def all_role_ids() -> tuple[str, ...]:
    """All known role ids in canonical (declaration) order."""
    return tuple(ROLE_OUTPUT_CLASSES.keys())


# ---------------------------------------------------------------------------
# Supervisor state
# ---------------------------------------------------------------------------


class SupervisorState(BaseModel):
    session_id: str
    task_marker: str
    persona_id: str
    intensity: Literal["light", "standard", "full"] = "standard"
    situation_id: str | None = None
    phase: Literal[
        "IDLE", "CLASSIFYING", "ROUTING", "DISPATCHING", "AWAITING_AGENT", "INTEGRATING", "DONE"
    ] = "IDLE"
    dispatched: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    backtrack_count: int = 0


class NextAction(BaseModel):
    action: Literal["classify", "dispatch", "dispatch_parallel", "backtrack", "done"]
    formula: str | None = None
    formulas: list[str] = Field(default_factory=list)
    input_slice: dict[str, Any] = Field(default_factory=dict)
    agent_file: str | None = None
    reason: str = ""
    advisory: str = ""  # Anti-Paralysis advisory text (empty when no warning)


# ---------------------------------------------------------------------------
# Phase N — Task Signals + Role chain
# Spec: docs/phase-n-role-based-routing-plan.md §2.1 and §2.3
# ---------------------------------------------------------------------------


class TaskSignals(BaseModel):
    domain: list[str] = Field(default_factory=list)
    action: Literal[
        "create",
        "modify",
        "debug",
        "research",
        "review",
        "deploy",
        "refactor",
        "document",
        "audit",
        "unknown",
    ] = "unknown"

    novelty: float = 0.0
    breaking_change: bool = False
    has_production_impact: bool = False
    has_unknowns: bool = False

    urgency: Literal["normal", "elevated", "incident"] = "normal"
    scope_size: Literal["trivial", "small", "medium", "large", "recursive"] = "medium"
    external_dependency: bool = False
    is_takeover: bool = False
    exhaustive: bool = False  # exhaustive-scope intent (.intent.json) — gates audit-exhaustive preset

    complexity: Literal["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC", "CONFUSION"] = "COMPLICATED"
    dimensions: int = 1
    evidence: dict[str, Any] = Field(default_factory=dict)
    extraction_ms: int = 0
    source_errors: list[str] = Field(default_factory=list)


class RoleActivation(BaseModel):
    """Output of the per-role scoring step in the composer."""

    role_id: str
    score: int
    matched_triggers: list[str] = Field(default_factory=list)
    skipped_deactivators: list[str] = Field(default_factory=list)


class ComposedChain(BaseModel):
    chain: list[str]
    source: Literal["preset", "composer", "situation", "fallback"]
    preset_id: str | None = None
    situation_id: str | None = None
    preset_version: str | None = None
    effective_threshold: int | None = None
    activations: list[RoleActivation] = Field(default_factory=list)
    parallel_roles: list[str] = Field(default_factory=list)
    reason: str = ""
    advisory: str = ""
