"""board_os workflow — state-machine edges, WIP columns, and result types.

Leaf module: every workflow sibling imports from here and it imports none of
them, so the transition table has one definition and the walkers stay acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Valid transition edges: {from_status: {to_statuses}}
# "ready" was a dedicated column in earlier versions — it has been folded
# into an `icebox + "ready" label` combination so the board has one less
# queue and "ready" becomes something the agent tags rather than a
# destination to drag tasks into.  Any legacy task still carrying
# status='ready' is migrated to 'icebox' via _migrate_v19_drop_ready_status.
# archive is *soft-terminal*: the only way out is back to icebox or complete,
# which is how a user recovers from an accidental archive.  Any other target
# requires an explicit --force flag (workflow.transition(..., force=True)) so
# mis-clicks still surface an error, but a human can always self-correct.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "icebox": {"in_progress", "emergency", "archive"},
    "emergency": {"in_progress", "icebox"},
    "in_progress": {"testing", "blocked", "icebox", "emergency", "complete"},
    "testing": {"complete", "in_progress", "blocked"},
    "complete": {"archive"},
    "blocked": {"in_progress", "emergency", "icebox"},
    "archive": {"icebox", "complete"},  # un-archive paths (see note above)
}

# Statuses that count toward the WIP cap for a given column.
_WIP_COLUMN_MAP: dict[str, str] = {
    "in_progress": "in_progress",
    "testing": "testing",
    "emergency": "emergency",
}


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    task_id: str
    previous_status: str | None
    new_status: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    wip_state: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class WipState:
    """Current WIP counts vs. configured caps per column."""

    counts: dict[str, int]
    caps: dict[str, int]
    violations: tuple[str, ...]

    def violates(self, column: str) -> bool:
        cap = self.caps.get(column)
        return cap is not None and self.counts.get(column, 0) >= cap


class TransitionError(ValueError):
    """Raised on invalid transitions. Carries suggested paths."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str,
        from_status: str,
        to_status: str,
        suggested: list[str] | None = None,
    ) -> None:
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status
        self.suggested = suggested or []
        super().__init__(message)
