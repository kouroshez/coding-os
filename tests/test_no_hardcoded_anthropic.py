"""Lint guard — no hardcoded Anthropic secrets / model IDs in source (T12.5)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Post src/-layout migration these live under src/ — the old bare
# ("core", "cli", "adapters") silently matched nothing, so the whole
# secret/model scan collected zero files and skipped.
GUARDED_DIRS = ("src/core", "src/cli", "src/adapters")

# Anthropic API key prefix per https://docs.anthropic.com/en/api/.
# `sk-ant-…` keys are 100+ chars; the prefix alone is enough to fail.
SECRET_PATTERN = re.compile(r"sk-ant-[a-zA-Z0-9_-]{8,}")

# Hardcoded model ids — the kernel must not embed these inline. Allow-list
# files where the inline reference is required for compatibility gating.
MODEL_PATTERN = re.compile(r"\bclaude-(?:opus|sonnet|haiku)-[0-9]+(?:-[0-9]+)?\b")
ALLOWED_MODEL_PATHS: set[str] = {
    "src/adapters/claude/_claude_sdk_options.py",  # xhigh-effort prefix gate
    "src/adapters/claude/adapter.yaml",  # adapter manifest
    "src/core/thinking_os/dispatcher.py",  # docstring example only
    "src/core/thinking_os/_db_migrations.py",  # migration docstring example
    "src/core/hooks/_helpers/presence_write.py",  # docstring example of the model arg
    "src/core/thinking_os/compress.py",  # COS_COMPRESS_MODEL env default
    "src/core/thinking_os/tests/test_compress.py",  # asserts _stamp_provenance echoes the model id
    "src/core/thinking_os/tests/test_record_outcome.py",  # writes .model fixture + asserts resolution
    "src/core/thinking_os/tests/test_dispatch_safety.py",  # asserts the dispatch row echoes the requested model
    "src/core/thinking_os/agents/researcher.md",  # role frontmatter
    "src/core/thinking_os/agents/implementer.md",
    "src/core/thinking_os/agents/reviewer.md",
    "src/core/thinking_os/agents/debugger.md",
    "src/core/thinking_os/agents/refactorer.md",
    "src/core/thinking_os/agents/analyst.md",
    "src/core/thinking_os/agents/architect.md",
    "src/core/thinking_os/agents/security_auditor.md",
    "src/core/thinking_os/agents/observer.md",
    "src/core/thinking_os/agents/deployer.md",
    "src/core/thinking_os/agents/documenter.md",
    "src/core/skills/llm-patterns/SKILL.md",  # model-selection guide doc (cross-cutting skill)
    "src/templates/meta/skills/claude-sdk-integration/SKILL.md",  # SDK-integration skill: documented model defaults
}


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for d in GUARDED_DIRS:
        for ext in ("*.py", "*.yaml", "*.md"):
            files.extend((REPO_ROOT / d).rglob(ext))
    return [f for f in files if "__pycache__" not in f.parts and "node_modules" not in f.parts]


@pytest.mark.parametrize(
    "source_file",
    _iter_source_files(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_no_hardcoded_anthropic_secrets_or_models(source_file: Path) -> None:
    text = source_file.read_text(encoding="utf-8", errors="ignore")
    rel = source_file.relative_to(REPO_ROOT).as_posix()

    # API key leak — never allowed anywhere.
    secret_match = SECRET_PATTERN.search(text)
    assert secret_match is None, (
        f"{rel}: Anthropic API key prefix {secret_match.group(0)[:14]}… "
        f"leaked into source. Move to .env / secret manager."
    )

    # Model id — allowed only in registry / adapter manifest / role frontmatter.
    if rel in ALLOWED_MODEL_PATHS:
        return
    model_match = MODEL_PATTERN.search(text)
    assert model_match is None, (
        f"{rel}: hardcoded model id {model_match.group(0)!r}. "
        f"Model selection must come from DispatchRequest.model / role "
        f"frontmatter / adapter.yaml — not inline. If this reference is "
        f"intentional (compatibility gate), add the path to "
        f"ALLOWED_MODEL_PATHS in tests/test_no_hardcoded_anthropic.py."
    )


def test_allowed_model_paths_all_exist() -> None:
    """Guard the allow-list itself — a renamed or deleted allowed file leaves
    a stale entry that silently shrinks the scan's coverage."""
    missing = sorted(p for p in ALLOWED_MODEL_PATHS if not (REPO_ROOT / p).exists())
    assert not missing, f"stale ALLOWED_MODEL_PATHS entries (file gone): {missing}"


def test_scan_actually_covers_files() -> None:
    """Guard the guard — if GUARDED_DIRS goes stale (e.g. a layout migration),
    _iter_source_files() returns [] and the secret/model scan silently skips."""
    files = _iter_source_files()
    assert len(files) > 50, f"source scan collected only {len(files)} files — GUARDED_DIRS stale?"


def _core_py_files() -> list[Path]:
    return [f for f in (REPO_ROOT / "src" / "core").rglob("*.py") if "__pycache__" not in f.parts]


def test_no_claude_agent_options_construction_in_core() -> None:
    """P8 anti-recurrence (TASK-472): src/core/** must never construct the adapter
    SDK type directly — ClaudeAgentOptions builds route through the adapter seam
    (claude_agent_options / claude_session_options in sdk_dispatcher.py). Catches
    both `ClaudeAgentOptions(...)` and `sdk.ClaudeAgentOptions(...)`."""
    import ast

    offenders: list[str] = []
    core_files = _core_py_files()
    for path in core_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "ClaudeAgentOptions":
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}")
    assert core_files, "no src/core/**.py scanned — layout drift?"
    assert not offenders, (
        "ClaudeAgentOptions constructed inside src/core/** (P8 violation) at "
        + ", ".join(offenders)
        + " — route through _build_agent_options / the adapter sdk_dispatcher seam."
    )
