from __future__ import annotations

from cli.hook_renderer import AdapterCapabilities, HookEntry, render_for_adapter


def test_resolve_matcher_keeps_supported_subset_for_codex_resume() -> None:
    caps = AdapterCapabilities(
        agent_id="codex",
        by_event={"SessionStart": ["startup", "resume"]},
    )

    assert caps.resolve_matcher("SessionStart", "startup") == "startup"
    assert caps.resolve_matcher("SessionStart", "compact|resume") == "resume"
    assert caps.resolve_matcher("SessionStart", "compact") is None


def test_resolve_matcher_preserves_full_matcher_when_adapter_supports_all_tokens() -> None:
    caps = AdapterCapabilities(
        agent_id="claude",
        by_event={"SessionStart": ["startup", "compact|resume"]},
    )

    assert caps.resolve_matcher("SessionStart", "compact|resume") == "compact|resume"


def test_render_for_adapter_replaces_group_with_dispatcher() -> None:
    registry = [
        HookEntry(
            id="block-secrets",
            script="block-secrets.sh",
            description="x",
            category="safety",
            phase="0",
            events=[{"event": "PreToolUse", "matcher": "Bash", "status_message": "a"}],
        ),
        HookEntry(
            id="enforce-verify",
            script="enforce-verify.sh",
            description="x",
            category="enforcement",
            phase="0",
            events=[{"event": "PreToolUse", "matcher": "Bash", "status_message": "b"}],
        ),
    ]
    caps = AdapterCapabilities(
        agent_id="codex",
        by_event={"PreToolUse": ["Bash"]},
        dispatchers={
            ("PreToolUse", "Bash"): {
                "script": "codex-pretool-dispatch.sh",
                "status_message": "dispatch",
                "delegates": ["block-secrets.sh", "enforce-verify.sh"],
            }
        },
    )

    rendered = render_for_adapter(registry, caps)
    hooks = rendered["hooks"]["PreToolUse"][0]["hooks"]

    assert len(hooks) == 1
    assert "/codex-pretool-dispatch.sh" in hooks[0]["command"]
    assert hooks[0]["command"].startswith("env COS_AGENT=codex ")
    assert hooks[0]["statusMessage"] == "dispatch"


def test_dispatcher_removes_delegates_from_overlapping_composite_matchers() -> None:
    registry = [
        HookEntry(
            id="remind-daily",
            script="remind-daily.sh",
            description="x",
            category="reminder",
            phase="0",
            events=[{"event": "SessionStart", "matcher": "resume"}],
        ),
        HookEntry(
            id="pr-reap",
            script="pr-reap.sh",
            description="x",
            category="meta",
            phase="0",
            events=[{"event": "SessionStart", "matcher": "startup|resume"}],
        ),
    ]
    delegates = ["remind-daily.sh", "pr-reap.sh"]
    caps = AdapterCapabilities(
        agent_id="codex",
        by_event={"SessionStart": ["startup", "compact|resume"]},
        dispatchers={
            ("SessionStart", "startup"): {
                "script": "codex-sessionstart-dispatch.sh",
                "delegates": delegates,
            },
            ("SessionStart", "compact|resume"): {
                "script": "codex-sessionstart-dispatch.sh",
                "delegates": delegates,
            },
        },
    )

    groups = render_for_adapter(registry, caps)["hooks"]["SessionStart"]

    assert [group["matcher"] for group in groups] == ["startup", "compact|resume"]
    assert all(
        "/codex-sessionstart-dispatch.sh" in group["hooks"][0]["command"]
        and group["hooks"][0]["command"].startswith("env COS_AGENT=codex ")
        for group in groups
    )


def test_dispatcher_keeps_same_script_on_non_overlapping_matcher() -> None:
    registry = [
        HookEntry(
            id="sync-task-current",
            script="sync-task-current.sh",
            description="x",
            category="task",
            phase="0",
            events=[
                {"event": "PostToolUse", "matcher": "Bash"},
                {"event": "PostToolUse", "matcher": "mcp__coding-os__cos_task_move"},
            ],
        )
    ]
    caps = AdapterCapabilities(
        agent_id="codex",
        by_event={"PostToolUse": ["Bash", "mcp__coding-os__cos_task_move"]},
        dispatchers={
            ("PostToolUse", "Bash"): {
                "script": "codex-posttool-dispatch.sh",
                "delegates": ["sync-task-current.sh"],
            }
        },
    )

    groups = render_for_adapter(registry, caps)["hooks"]["PostToolUse"]

    mcp_group = next(
        group for group in groups if group["matcher"] == "mcp__coding-os__cos_task_move"
    )
    assert "/sync-task-current.sh" in mcp_group["hooks"][0]["command"]
    assert mcp_group["hooks"][0]["command"].startswith("env COS_AGENT=codex ")


def test_dispatcher_does_not_drop_partially_covered_composite_matcher() -> None:
    registry = [
        HookEntry(
            id="recover",
            script="recover.sh",
            description="x",
            category="task",
            phase="0",
            events=[{"event": "SessionStart", "matcher": "startup|resume"}],
        )
    ]
    caps = AdapterCapabilities(
        agent_id="codex",
        by_event={"SessionStart": ["startup", "resume"]},
        dispatchers={
            ("SessionStart", "startup"): {
                "script": "startup-dispatch.sh",
                "delegates": ["recover.sh"],
            }
        },
    )

    groups = render_for_adapter(registry, caps)["hooks"]["SessionStart"]

    composite = next(group for group in groups if group["matcher"] == "startup|resume")
    assert "/recover.sh" in composite["hooks"][0]["command"]
    assert composite["hooks"][0]["command"].startswith("env COS_AGENT=codex ")


def test_direct_hook_commands_establish_each_adapter_identity() -> None:
    registry = [
        HookEntry(
            id="presence",
            script="agent-presence.sh",
            description="x",
            category="observability",
            phase="0",
            events=[{"event": "SessionEnd", "matcher": ""}],
        )
    ]

    for agent_id in ("claude", "codex"):
        caps = AdapterCapabilities(agent_id=agent_id, by_event={"SessionEnd": [""]})
        command = render_for_adapter(registry, caps)["hooks"]["SessionEnd"][0]["hooks"][0][
            "command"
        ]
        assert command == f'env COS_AGENT={agent_id} "{{{{HOOKS_DIR}}}}/agent-presence.sh"'


def test_render_for_adapter_records_parity_deficit_not_silent_drop() -> None:
    # A Write|Edit enforce gate a Bash-only adapter cannot fire must surface as
    # a parity deficit, not vanish silently (N1) — and never leak into the
    # emitted template.
    registry = [
        HookEntry(
            id="enforce-skill",
            script="enforce-skill.sh",
            description="x",
            category="enforcement",
            phase="0",
            events=[{"event": "PreToolUse", "matcher": "Write|Edit"}],
        ),
    ]
    caps = AdapterCapabilities(agent_id="codex", by_event={"PreToolUse": ["Bash"]}, dispatchers={})

    rendered = render_for_adapter(registry, caps)

    deficits = rendered.get("_parity_deficits", [])
    assert any(d["hook"] == "enforce-skill" for d in deficits)
    assert deficits[0]["adapter"] == "codex"
    # The deficit is a diagnostic, never part of the rendered hooks.
    assert not rendered["hooks"]
