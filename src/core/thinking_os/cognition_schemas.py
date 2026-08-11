"""Coding OS — Cognitive agent IO contracts."""

from __future__ import annotations

from typing import Any, Literal

from _cognition_artifacts import (
    ADR as ADR,
    Actor as Actor,
    AmbiguityCriterion as AmbiguityCriterion,
    ConceptualModel as ConceptualModel,
    DecisionTable as DecisionTable,
    DependencyGraph as DependencyGraph,
    DeployStep as DeployStep,
    EventDef as EventDef,
    GoalNode as GoalNode,
    Metric as Metric,
    MonitorAlert as MonitorAlert,
    PermissionMatrix as PermissionMatrix,
    RefactorItem as RefactorItem,
    Scenario as Scenario,
    SecurityFinding as SecurityFinding,
    StateMachine as StateMachine,
    TestCase as TestCase,
    Unknown as Unknown,
)
from pydantic import BaseModel, Field

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
# Task Signals + Role chain
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


class DistilledLesson(BaseModel):
    """Output of the friction-cluster distiller (agents/distiller.md)."""

    situation: str = Field(min_length=10, max_length=160)
    action: str = Field(min_length=10, max_length=200)
    why: str = Field(min_length=5, max_length=160)


class SessionSummaryFacts(BaseModel):
    """Session-level narrative distilled by the session observer (item A)."""

    investigated: str = Field(default="", max_length=400)
    learned: str = Field(default="", max_length=400)
    next_steps: str = Field(default="", max_length=400)
    has_signal: bool = False


class ObservationEnrichment(BaseModel):
    """One mechanical observation distilled into recallable semantic fields."""

    observation_id: int
    narrative: str = Field(default="", max_length=400)
    concepts: list[str] = Field(default_factory=list, max_length=8)
    has_signal: bool = False


class SessionEnrichment(BaseModel):
    """Full output of the session observer (agents/session_observer.md)."""

    observations: list[ObservationEnrichment] = Field(default_factory=list, max_length=20)
    summary: SessionSummaryFacts = Field(default_factory=SessionSummaryFacts)
