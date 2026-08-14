"""Where Claude Code keeps this project's transcripts.

The kernel used to `from claude_agent_sdk import project_key_for_directory`
directly, which is an adapter SDK import inside `src/core/**` (P8). The
knowledge of how one runtime names its transcript directory belongs here, next
to the rest of that runtime's translation layer.
"""

from __future__ import annotations

from pathlib import Path


def project_key(project_root: str | Path) -> str:
    """Directory name under ~/.claude/projects for this working directory."""
    root = Path(project_root)
    try:
        from claude_agent_sdk import project_key_for_directory

        return str(project_key_for_directory(root))
    except Exception:
        # The SDK is an optional extra; its key derivation is a plain path
        # mangling, so reproduce it rather than losing presence entirely.
        return "-" + str(root).replace("/", "-").lstrip("-")


def transcript_dir(project_root: str | Path) -> Path:
    return Path.home() / ".claude" / "projects" / project_key(project_root)
