"""board-os — the Scrumban task subsystem of coding-os.

Sibling to thinking-os and graph-os. Owns task workflow state
(extended `tasks` columns + `task_status_history`, shared SQLite
DB, migration v13) plus the per-project `scrumban-config.yaml`
that defines swimlanes, WIP caps, and label families.

Public surface (L.0):
  ScrumbanConfig        — Pydantic model for .coding-os/scrumban-config.yaml
  load_config           — locate + parse the per-project config (config.py)
  ConfigValidationError — raised on schema violations
  KIND_ENUM             — closed enum of work types (drives card colour)
  STATUS_ENUM           — closed enum of workflow columns
  PRIORITY_ENUM         — closed enum P0..P3

L.0 scope is schema + config + lean templates + per-stack defaults.
Workflow engine, MCP tools, hooks, viewer, CLI, and migration tooling
ship in later slices (see docs/phase-l-scrumban-task-system-plan.md
Section 19).
"""

from core.board_os.config import (
    KIND_ENUM,
    PRIORITY_ENUM,
    STATUS_ENUM,
    ConfigValidationError,
    ScrumbanConfig,
    load_config,
)

__all__ = [
    "KIND_ENUM",
    "PRIORITY_ENUM",
    "STATUS_ENUM",
    "ConfigValidationError",
    "ScrumbanConfig",
    "load_config",
]
