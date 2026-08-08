"""Hook registry → adapter rendering integration test (TASK-162 fix #5)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "src" / "core" / "hooks" / "registry.yaml"
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"
CLAUDE_TEMPLATE = REPO_ROOT / "src" / "adapters" / "claude" / "settings.template.json"


def _load_registry() -> list[dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return list(data.get("hooks") or [])


def _flatten_claude_template(data: dict) -> set[tuple[str, str, str]]:
    """Return {(event, matcher, command)} triples from the claude template."""
    out: set[tuple[str, str, str]] = set()
    hooks = data.get("hooks") or {}
    for event, entries in hooks.items():
        for entry in entries:
            matcher = entry.get("matcher", "")
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                out.add((event, matcher, cmd))
    return out


def test_every_registry_script_exists_on_disk() -> None:
    missing: list[str] = []
    for entry in _load_registry():
        script = entry.get("script", "")
        if not script:
            continue
        # adapter_scope entries ship from src/adapters/<scope>/hooks/, not the
        # agent-agnostic core dir (e.g. the claude-only agent-memory pair).
        scope = entry.get("adapter_scope", "")
        script_dir = REPO_ROOT / "src" / "adapters" / scope / "hooks" if scope else HOOKS_DIR
        if not (script_dir / script).is_file():
            missing.append(f"{entry.get('id')} → {script}")
    assert not missing, f"Registry references missing scripts: {missing}"


def _claude_capabilities() -> dict[str, set[str]]:
    """Read claude adapter.yaml::hook_capabilities → {event: {matchers}}."""
    adapter = REPO_ROOT / "src" / "adapters" / "claude" / "adapter.yaml"
    data = yaml.safe_load(adapter.read_text(encoding="utf-8"))
    raw = data.get("hook_capabilities") or {}
    return {ev: set(spec.get("matchers") or []) for ev, spec in raw.items()}


def test_claude_template_renders_every_supported_registry_event() -> None:
    """Each `(hook_id, event, matcher)` triple in the registry whose pair
    is declared supported by `adapters/claude/adapter.yaml::hook_capabilities`
    MUST appear in the rendered claude template. Pairs the adapter cannot
    fire are intentionally skipped by the renderer (adapter-parity rule)."""
    template = json.loads(CLAUDE_TEMPLATE.read_text(encoding="utf-8"))
    rendered = _flatten_claude_template(template)
    # Rendered commands carry an `env COS_AGENT=<id>` prefix and quote the
    # script path — strip both down to the script basename before matching.
    rendered_index = {
        (event, matcher, Path(cmd.strip().strip('"')).name) for event, matcher, cmd in rendered
    }
    capabilities = _claude_capabilities()

    missing: list[str] = []
    for entry in _load_registry():
        script = entry.get("script", "")
        for ev in entry.get("events") or []:
            event = ev.get("event")
            matcher = ev.get("matcher") or ""
            if not event:
                continue
            supported = capabilities.get(event, set())
            if matcher not in supported:
                continue  # renderer correctly skips unsupported pair
            if (event, matcher, script) not in rendered_index:
                missing.append(f"{entry.get('id')} {event}::{matcher} → {script}")
    assert not missing, (
        "Supported registry events missing from rendered claude template: " + ", ".join(missing)
    )


def test_registry_yaml_is_valid_yaml() -> None:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "hooks" in data
    assert isinstance(data["hooks"], list)
    for entry in data["hooks"]:
        assert "id" in entry
        assert "script" in entry
        assert "events" in entry


def test_hook_ids_are_unique() -> None:
    ids = [entry.get("id") for entry in _load_registry()]
    duplicates = [hid for hid in set(ids) if ids.count(hid) > 1]
    assert not duplicates, f"Duplicate hook ids in registry: {duplicates}"


# ---------------------------------------------------------------------------
# stdin → behavior end-to-end
# ---------------------------------------------------------------------------


import subprocess
import textwrap


def _run_hook(script: Path, payload: dict, env: dict | None = None) -> tuple[int, str, str]:
    """Invoke a hook script with the given JSON payload on stdin."""
    proc = subprocess.run(
        ["bash", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, **(env or {})},
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_enforce_scaffold_boundary_blocks_forbidden_subtree(tmp_path: Path) -> None:
    boundary = tmp_path / "scaffold-boundary.yaml"
    boundary.write_text(
        textwrap.dedent(
            """
            version: 1
            stacks:
              - stack: nextjs
                roots: [frontend/]
                file_patterns: ["frontend/**/*.tsx"]
                imports_from: [shared/]
                forbids_writing_in: [mobile/, backend/]
              - stack: react-native
                roots: [mobile/]
                file_patterns: ["mobile/**/*.tsx"]
                imports_from: [shared/]
                forbids_writing_in: [frontend/, backend/]
            """
        ).strip(),
        encoding="utf-8",
    )
    rc, _, stderr = _run_hook(
        REPO_ROOT / "src" / "core" / "hooks" / "enforce-scaffold-boundary.sh",
        {"tool_name": "Write", "tool_input": {"file_path": "mobile/foo.swift"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 2, f"Expected block (exit 2), got rc={rc}; stderr={stderr!r}"
    assert "BLOCKED:" in stderr


def test_enforce_scaffold_boundary_allows_owned_path(tmp_path: Path) -> None:
    boundary = tmp_path / "scaffold-boundary.yaml"
    boundary.write_text(
        textwrap.dedent(
            """
            version: 1
            stacks:
              - stack: nextjs
                roots: [frontend/]
                file_patterns: ["frontend/**/*.tsx"]
                imports_from: [shared/]
                forbids_writing_in: [mobile/]
            """
        ).strip(),
        encoding="utf-8",
    )
    rc, _, stderr = _run_hook(
        REPO_ROOT / "src" / "core" / "hooks" / "enforce-scaffold-boundary.sh",
        {"tool_name": "Write", "tool_input": {"file_path": "frontend/foo.tsx"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0, f"Expected pass (exit 0), got rc={rc}; stderr={stderr!r}"


def test_enforce_scaffold_boundary_no_policy_means_no_enforcement(tmp_path: Path) -> None:
    rc, _, stderr = _run_hook(
        REPO_ROOT / "src" / "core" / "hooks" / "enforce-scaffold-boundary.sh",
        {"tool_name": "Write", "tool_input": {"file_path": "mobile/foo.swift"}},
        env={
            "COS_STATE_DIR": str(tmp_path),  # boundary file absent
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0, f"Expected pass (no policy), got rc={rc}; stderr={stderr!r}"


def test_auto_regen_doc_index_dispatches_for_docs_md(tmp_path: Path) -> None:
    rc, _, _ = _run_hook(
        REPO_ROOT / "src" / "core" / "hooks" / "auto-regen-doc-index.sh",
        {"tool_name": "Edit", "tool_input": {"file_path": "docs/governance/critical-rules.md"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0


def test_auto_regen_doc_index_skips_non_md(tmp_path: Path) -> None:
    rc, _, _ = _run_hook(
        REPO_ROOT / "src" / "core" / "hooks" / "auto-regen-doc-index.sh",
        {"tool_name": "Edit", "tool_input": {"file_path": "src/core/thinking_os/database.py"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0
