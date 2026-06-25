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
    assert hooks[0]["command"].endswith("/codex-pretool-dispatch.sh")
    assert hooks[0]["statusMessage"] == "dispatch"


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
