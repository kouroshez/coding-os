"""Lint guard — no hardcoded Anthropic secrets / model IDs in source (T12.5)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

GUARDED_DIRS = ("core", "cli", "adapters")

# Anthropic API key prefix per https://docs.anthropic.com/en/api/.
# `sk-ant-…` keys are 100+ chars; the prefix alone is enough to fail.
SECRET_PATTERN = re.compile(r"sk-ant-[a-zA-Z0-9_-]{8,}")

# Hardcoded model ids — the kernel must not embed these inline. Allow-list
# files where the inline reference is required for compatibility gating.
MODEL_PATTERN = re.compile(
    r"\bclaude-(?:opus|sonnet|haiku)-[0-9]+(?:-[0-9]+)?\b"
)
ALLOWED_MODEL_PATHS: set[str] = {
    "adapters/claude/sdk_dispatcher.py",       # _OPUS_47_MODEL_IDS gate
    "adapters/claude/adapter.yaml",            # adapter manifest
    "core/thinking_os/dispatcher.py",          # docstring example only
    "core/thinking_os/db.py",                  # migration docstring example
    "core/thinking_os/compress.py",            # COS_COMPRESS_MODEL env default
    "core/thinking_os/agents/researcher.md",   # role frontmatter
    "core/thinking_os/agents/implementer.md",
    "core/thinking_os/agents/reviewer.md",
    "core/thinking_os/agents/debugger.md",
    "core/thinking_os/agents/refactorer.md",
    "core/thinking_os/agents/analyst.md",
    "core/thinking_os/agents/architect.md",
    "core/thinking_os/agents/security_auditor.md",
    "core/thinking_os/agents/observer.md",
    "core/thinking_os/agents/deployer.md",
    "core/thinking_os/agents/documenter.md",
}


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for d in GUARDED_DIRS:
        for ext in ("*.py", "*.yaml", "*.md"):
            files.extend((REPO_ROOT / d).rglob(ext))
    return [
        f for f in files
        if "__pycache__" not in f.parts and "node_modules" not in f.parts
    ]


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
