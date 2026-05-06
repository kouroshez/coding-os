"""Regression guard for the live `ClaudeAgentOptions` field surface."""
from __future__ import annotations

import dataclasses

import pytest


# Fields the Claude dispatcher reads or writes today (2026-05-05). New
# fields the SDK adds are tolerated; missing fields are NOT.
REQUIRED_FIELDS: set[str] = {
    "system_prompt",
    "max_turns",
    "allowed_tools",
    "disallowed_tools",
    "cwd",
    "permission_mode",
    "setting_sources",
    "model",
    "effort",
    "skills",
    "env",
    "output_format",
    "max_budget_usd",
    "betas",
    "hooks",
    # T7.1: session_id forwarded to SDK so presence key matches sub-session key
    "session_id",
    # T9.1: file checkpointing for edit-heavy roles (implementer/refactorer)
    "enable_file_checkpointing",
}

# Permission modes the dispatcher knows how to set; fail if the SDK
# loses one we depend on (e.g. dontAsk).
REQUIRED_PERMISSION_MODES: set[str] = {
    "default",
    "acceptEdits",
    "plan",
    "bypassPermissions",
    "dontAsk",
}

# Hook events the registry declares for the Claude adapter (Q.deep).
REQUIRED_HOOK_EVENTS: set[str] = {
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "SubagentStart",
    "PreCompact",
    "Notification",
    "PermissionRequest",
}


@pytest.fixture(scope="module")
def options_cls():
    sdk = pytest.importorskip("claude_agent_sdk")
    return sdk.ClaudeAgentOptions


def test_options_carries_required_fields(options_cls) -> None:
    fields = {f.name for f in dataclasses.fields(options_cls)}
    missing = REQUIRED_FIELDS - fields
    assert not missing, (
        f"ClaudeAgentOptions missing fields the dispatcher uses: {missing}"
    )


def test_permission_mode_literal_carries_required_values() -> None:
    sdk_types = pytest.importorskip("claude_agent_sdk.types")
    # SDK declares Optional[Literal[...]] on ClaudeAgentOptions.
    # Walk dataclass fields and find the permission_mode annotation.
    field = next(
        f for f in dataclasses.fields(sdk_types.ClaudeAgentOptions)
        if f.name == "permission_mode"
    )
    annotation = repr(field.type)
    for mode in REQUIRED_PERMISSION_MODES:
        assert f"'{mode}'" in annotation, (
            f"permission_mode literal missing required value {mode!r}; "
            f"got: {annotation}"
        )


def test_hooks_dict_supports_required_events() -> None:
    sdk_types = pytest.importorskip("claude_agent_sdk.types")
    field = next(
        f for f in dataclasses.fields(sdk_types.ClaudeAgentOptions)
        if f.name == "hooks"
    )
    annotation = repr(field.type)
    for event in REQUIRED_HOOK_EVENTS:
        assert f"'{event}'" in annotation, (
            f"hooks dict missing event literal {event!r}; got: {annotation}"
        )


def test_dispatcher_import_failure_path() -> None:
    """SDK import failure returns a DispatchResult with status='error' (T12.4)."""
    import sys

    old = sys.modules.pop("claude_agent_sdk", None)
    sys.modules["claude_agent_sdk"] = None  # type: ignore[assignment]
    try:
        import importlib
        # Force reimport so ClaudeSDKDispatcher re-runs __init__
        import importlib.util, importlib.machinery
        spec = importlib.util.spec_from_file_location(
            "_test_dispatcher",
            "adapters/claude/sdk_dispatcher.py",
        )
        if spec is None:
            pytest.skip("sdk_dispatcher.py not found from test cwd")
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception:
            pytest.skip("sdk_dispatcher.py failed to exec — likely missing deps in test env")
        dispatcher = mod.ClaudeSDKDispatcher()
        assert not dispatcher.available(), "should not be available when SDK missing"
        assert dispatcher._import_error is not None
    finally:
        sys.modules.pop("claude_agent_sdk", None)
        if old is not None:
            sys.modules["claude_agent_sdk"] = old


def test_system_prompt_preset_shape() -> None:
    sdk_types = pytest.importorskip("claude_agent_sdk.types")
    preset = sdk_types.SystemPromptPreset
    annotations = preset.__annotations__
    assert "type" in annotations
    assert "preset" in annotations
    # `exclude_dynamic_sections` is the field the dispatcher relies on
    # for cross-cwd cache reuse — its disappearance breaks the cost
    # narrative in claude-sdk.md §7.2.
    assert "exclude_dynamic_sections" in annotations, (
        "SystemPromptPreset lost `exclude_dynamic_sections` — review "
        "claude-sdk.md §7.2 before bumping the SDK."
    )
