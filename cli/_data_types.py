"""Immutable data types for the stack/adapter aggregation pipeline.

All dataclasses are frozen so aggregation is a pure function: no hidden
mutation, fully testable, deterministic output for a given input.

These types are shared across:

    cli/stack_registry.py     → produces StackProfile
    cli/adapter_registry.py   → produces AdapterProfile
    cli/aggregator.py         → consumes both, returns AggregatedWorld
    cli/renderer.py           → consumes AggregatedWorld
    cli/main.py, add_stack.py → orchestrates them

Design note: tuples (not lists) are used for sequence fields so instances
remain hashable and protected from accidental mutation after construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class VerifyRow:
    """One row in the AGENTS.md Verification Matrix."""
    glob: str
    suites: str
    cmd: str

    def key(self) -> tuple[str, str]:
        """Dedupe key for merging across stacks."""
        return (self.glob, self.suites)


@dataclass(frozen=True)
class RefCode:
    """One entry in the REF: shortcodes table."""
    code: str
    path: str
    desc: str


@dataclass(frozen=True)
class MakefileTarget:
    """One target contributed to the project root Makefile."""
    name: str
    cmd: str
    help: str = ""


@dataclass(frozen=True)
class RuleEntry:
    """Path-scoped rule file a stack contributes.

    `file` is relative to the stack's source_dir (e.g. "rules/backend.md").
    `globs` are the file-match patterns the rule auto-loads on.
    """
    file: str
    globs: tuple[str, ...]
    always_load: bool = False
    priority: int = 0


@dataclass(frozen=True)
class DimensionEntry:
    """One row in the dimension-registry.md generated doc."""
    stack_id: str
    name: str
    read_files: tuple[str, ...]
    depth: str = "M"  # L/M/D


@dataclass(frozen=True)
class SkillEnforcementEntry:
    """One row in the skill-enforcement.md generated doc."""
    stack_id: str
    globs: tuple[str, ...]
    primary: str
    secondary: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentsMdSection:
    """A fragment template to be rendered into AGENTS.md.

    `order` controls the position in the final document (ascending).
    `template` is relative to the owning profile's source_dir.
    `owner_dir` is resolved at registry load time so the renderer can
    locate the fragment file.
    """
    id: str
    order: int
    template: str
    owner_dir: Path


@dataclass(frozen=True)
class HookEntry:
    """A hook a stack (or adapter default) contributes to settings.json."""
    event: str         # PreToolUse, PostToolUse, Stop, SessionStart, …
    matcher: str       # tool-name pattern ("*", "Write|Edit", …)
    command: str       # shell command the harness runs


@dataclass(frozen=True)
class StackProfile:
    """Everything a stack contributes. Loaded from templates/<id>/stack.yaml."""
    id: str
    label: str
    category: str
    primary_skill: str | None
    skills: tuple[str, ...]
    substitutions: dict[str, str]
    verify: tuple[VerifyRow, ...]
    routing_entries: tuple[str, ...]
    ref_codes: tuple[RefCode, ...]
    makefile_targets: tuple[MakefileTarget, ...]
    rules: tuple[RuleEntry, ...]
    dimensions: tuple[DimensionEntry, ...]
    skill_enforcement: tuple[SkillEnforcementEntry, ...]
    agents_md_sections: tuple[AgentsMdSection, ...]
    hooks: tuple[HookEntry, ...]
    source_dir: Path


@dataclass(frozen=True)
class BaseProfile:
    """The agent-agnostic core profile. Loaded from templates/_base/base.yaml.

    Structurally identical to StackProfile minus `category` and
    `primary_skill` — base is never 'a stack' but it contributes the
    same kind of data (sections, verify rows, ref codes, …).
    """
    id: str
    label: str
    skills: tuple[str, ...]
    substitutions: dict[str, str]
    verify: tuple[VerifyRow, ...]
    routing_entries: tuple[str, ...]
    ref_codes: tuple[RefCode, ...]
    makefile_targets: tuple[MakefileTarget, ...]
    rules: tuple[RuleEntry, ...]
    dimensions: tuple[DimensionEntry, ...]
    skill_enforcement: tuple[SkillEnforcementEntry, ...]
    agents_md_sections: tuple[AgentsMdSection, ...]
    hooks: tuple[HookEntry, ...]
    source_dir: Path


@dataclass(frozen=True)
class McpLaunchConfigPath:
    """One location the doctor should probe for a coding-os MCP launch config."""
    scope: str          # "project" | "home"
    path: str           # relative to scope


@dataclass(frozen=True)
class McpLaunchSpec:
    """Data-driven C15 (MCP launch) metadata from adapter.yaml::mcp_launch."""
    loader: str                                         # "claude_json" | "codex_toml"
    config_paths: tuple[McpLaunchConfigPath, ...]


@dataclass(frozen=True)
class AdapterProfile:
    """Everything an agent adapter declares. Loaded from adapters/<id>/adapter.yaml."""
    id: str
    label: str
    settings_file: str | None
    hooks_dir: str | None
    rules_dir: str | None
    skills_dir: str | None
    commands_dir: str | None
    sourced_hooks: tuple[str, ...]
    supports_rules: bool
    supports_settings_json: bool
    install_script: Path
    default_settings: dict  # raw dict, deep-merged by renderer
    source_dir: Path
    mcp_helper: str | None = None         # relative path (from adapters/<id>/) to MCP install helper, if any
    mcp_launch: McpLaunchSpec | None = None
    # Env vars whose presence identifies this agent's runtime.  Read by
    # cli/board_commands.py::_detect_agent_runtime so the CLI can attribute
    # task transitions without hardcoded adapter-name literals (rule #11).
    runtime_env_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class AggregatedWorld:
    """The result of merging base + stacks + adapter.

    Passed as Jinja2 context to every fragment renderer. Pure data —
    no filesystem access, no mutation. Deterministic for a given input.
    """
    project_name: str
    agent_id: str
    stack_ids: tuple[str, ...]
    substitutions: dict[str, str]
    skills: tuple[str, ...]
    verify_rows: tuple[VerifyRow, ...]
    routing_entries: tuple[str, ...]
    ref_codes: tuple[RefCode, ...]
    makefile_targets: tuple[MakefileTarget, ...]
    rules: tuple[RuleEntry, ...]
    dimensions: tuple[DimensionEntry, ...]
    skill_enforcement: tuple[SkillEnforcementEntry, ...]
    agents_md_sections: tuple[AgentsMdSection, ...]
    hooks: tuple[HookEntry, ...]
    conflicts: tuple[str, ...] = field(default_factory=tuple)
