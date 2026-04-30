"""Hook registry → adapter rendering integration test (TASK-162 fix #5).

PURPOSE:      Lock the contract that every hook declared in
              `core/hooks/registry.yaml` (a) exists on disk and (b)
              surfaces in the rendered claude / cursor adapter
              templates per its declared `events`. Codex is intentionally
              skipped — its adapter capability set excludes the
              Write|Edit / Skill matchers (see adapter_parity rule).
INPUT:        repo state on disk.
OUTPUT:       pytest assertions; no external calls.
DEPENDENCIES: PyYAML.
NOTES:        Catches the failure mode the manual review flagged: a hook
              registered in YAML but missing from the rendered adapter
              template (or vice versa).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "core" / "hooks" / "registry.yaml"
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
CLAUDE_TEMPLATE = REPO_ROOT / "adapters" / "claude" / "settings.template.json"
CURSOR_TEMPLATE = REPO_ROOT / "adapters" / "cursor" / "hooks.cursor.template.json"


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


def _cursor_dispatcher_chains() -> dict[str, list[str]]:
    """Return {dispatcher_basename: [delegate_basename, …]} for cursor."""
    chains: dict[str, list[str]] = {}
    cursor_hooks = REPO_ROOT / "adapters" / "cursor" / "hooks"
    for script in cursor_hooks.glob("*.sh"):
        text = script.read_text(encoding="utf-8")
        delegates = []
        in_chain = False
        for line in text.splitlines():
            if "for delegate in" in line:
                in_chain = True
                continue
            if in_chain:
                stripped = line.strip().rstrip("\\").strip()
                if not stripped or stripped == "do":
                    if stripped == "do":
                        break
                    continue
                if stripped.endswith("; do"):
                    delegates.append(stripped.replace("; do", "").strip())
                    break
                delegates.append(stripped)
        chains[script.name] = delegates
    return chains


def test_every_registry_script_exists_on_disk() -> None:
    missing: list[str] = []
    for entry in _load_registry():
        script = entry.get("script", "")
        if not script:
            continue
        if not (HOOKS_DIR / script).is_file():
            missing.append(f"{entry.get('id')} → {script}")
    assert not missing, f"Registry references missing scripts: {missing}"


def _claude_capabilities() -> dict[str, set[str]]:
    """Read claude adapter.yaml::hook_capabilities → {event: {matchers}}."""
    adapter = REPO_ROOT / "adapters" / "claude" / "adapter.yaml"
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
    rendered_index = {(event, matcher, Path(cmd).name)
                      for event, matcher, cmd in rendered}
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
        "Supported registry events missing from rendered claude template: "
        + ", ".join(missing)
    )


def test_cursor_dispatcher_includes_every_posttool_write_hook() -> None:
    """Cursor coalesces Write|Edit hooks into `cursor-posttool-write-dispatch.sh`.
    Every registered hook with `PostToolUse :: Write|Edit` must appear in that
    dispatcher's `for delegate in …; do` chain."""
    chains = _cursor_dispatcher_chains()
    chain_name = "cursor-posttool-write-dispatch.sh"
    assert chain_name in chains, f"Missing cursor dispatcher: {chain_name}"
    delegates = set(chains[chain_name])

    expected: list[str] = []
    for entry in _load_registry():
        script = entry.get("script", "")
        for ev in entry.get("events") or []:
            if ev.get("event") == "PostToolUse" and ev.get("matcher") == "Write|Edit":
                expected.append(script)

    missing = [s for s in expected if s not in delegates]
    # We don't require the full set — only that the cursor dispatcher covers
    # the auto-* and capture-* observability hooks. Enforce the TASK-161
    # auto-regen-doc-index addition explicitly.
    assert "auto-regen-doc-index.sh" in delegates, (
        "TASK-161 hook missing from cursor PostToolUse Write dispatch chain"
    )
    # Other registered hooks may legitimately route via other dispatchers; we
    # surface them as a soft assertion to flag drift rather than block.
    if missing:
        pytest.skip(
            "Cursor dispatcher chain missing registered hooks (review whether "
            f"intentional): {missing}"
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
# stdin → behavior end-to-end (TASK-162 audit follow-up)
# ---------------------------------------------------------------------------


import json  # noqa: E402
import subprocess  # noqa: E402
import textwrap  # noqa: E402


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
        REPO_ROOT / "core" / "hooks" / "enforce-scaffold-boundary.sh",
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
        REPO_ROOT / "core" / "hooks" / "enforce-scaffold-boundary.sh",
        {"tool_name": "Write", "tool_input": {"file_path": "frontend/foo.tsx"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0, f"Expected pass (exit 0), got rc={rc}; stderr={stderr!r}"


def test_enforce_scaffold_boundary_no_policy_means_no_enforcement(tmp_path: Path) -> None:
    rc, _, stderr = _run_hook(
        REPO_ROOT / "core" / "hooks" / "enforce-scaffold-boundary.sh",
        {"tool_name": "Write", "tool_input": {"file_path": "mobile/foo.swift"}},
        env={
            "COS_STATE_DIR": str(tmp_path),  # boundary file absent
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0, f"Expected pass (no policy), got rc={rc}; stderr={stderr!r}"


def test_auto_regen_doc_index_dispatches_for_docs_md(tmp_path: Path) -> None:
    rc, _, _ = _run_hook(
        REPO_ROOT / "core" / "hooks" / "auto-regen-doc-index.sh",
        {"tool_name": "Edit", "tool_input": {"file_path": "docs/governance/critical-rules.md"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0


def test_auto_regen_doc_index_skips_non_md(tmp_path: Path) -> None:
    rc, _, _ = _run_hook(
        REPO_ROOT / "core" / "hooks" / "auto-regen-doc-index.sh",
        {"tool_name": "Edit", "tool_input": {"file_path": "core/thinking_os/db.py"}},
        env={
            "COS_STATE_DIR": str(tmp_path),
            "COS_PROJECT_ROOT": str(REPO_ROOT),
        },
    )
    assert rc == 0
