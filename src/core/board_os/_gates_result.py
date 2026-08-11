"""Transition Gate validation result types (TASK-104)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# ────────────────────────────────────────────────────────────────────
# Result types
# ────────────────────────────────────────────────────────────────────


class Verdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ValidationMessage(BaseModel):
    code: str  # stable identifier (e.g. "DOR_OUTCOME_MISSING")
    severity: Verdict
    field: str | None = None
    message: str  # human-readable repair hint


class ValidationResult(BaseModel):
    verdict: Verdict = Verdict.PASS
    messages: list[ValidationMessage] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.verdict is Verdict.BLOCK

    def add(self, msg: ValidationMessage) -> None:
        self.messages.append(msg)
        # Verdict escalates: PASS → WARN → BLOCK; never demotes.
        if msg.severity is Verdict.BLOCK:
            self.verdict = Verdict.BLOCK
        elif msg.severity is Verdict.WARN and self.verdict is Verdict.PASS:
            self.verdict = Verdict.WARN
