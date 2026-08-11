"""Coding OS — Cognitive artifact value types."""

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
