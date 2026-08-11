"""System-prompt construction for the Hub chat routes.

The chat framing, the role-agent append, and the onboarding-intake priming
change with what the assistant should KNOW, while the streaming routes change
with the SDK's event surface. A leaf — it imports no sibling route module.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CHAT_SYSTEM = (
    "You are the coding-os Hub chat assistant — a direct, helpful conversational "
    "agent for this project. Answer the user's message conversationally in Markdown. "
    "Do NOT prepend the transparency banner (the line starting with the bell emoji) "
    "and skip any cognitive-state / gate / work-log ceremony — that protocol is for "
    "terminal sessions, not Hub chat; just answer. You MAY use the cos_* tools "
    "(memory, graph, docs, board) to ground an answer when it genuinely helps, but "
    "keep replies focused and readable rather than running a full work protocol. "
    "When you commit code for a specific task, include its id like `(TASK-NNN)` in "
    "the commit subject so the board links the commit to that task."
)


def _role_system_prompt(role: str | None):
    """Load a role's agent prompt as a claude_code system-prompt append, if valid."""
    import re as _re

    if not role or not _re.match(r"^[a-z_]+$", role):
        return None
    agent_md = Path(__file__).resolve().parents[2] / "thinking_os" / "agents" / f"{role}.md"
    try:
        if agent_md.exists():
            return {
                "type": "preset",
                "preset": "claude_code",
                "append": agent_md.read_text(encoding="utf-8"),
            }
    except OSError:
        pass
    return None


def _role_names(agents_dir: Path) -> list[str]:
    import re as _re

    try:
        return sorted(
            p.stem
            for p in agents_dir.glob("*.md")
            if _re.match(r"^[a-z_]+$", p.stem) and not p.stem.startswith("_")
        )
    except OSError as exc:
        logger.debug("roles scan skipped %s: %s", agents_dir, exc)
        return []


def _prime_with_project_description(system_prompt: dict, cwd: str) -> dict:
    """Append the onboarding intake (docs/_meta/project-description.md) to the
    chat system prompt so the first session knows what the project IS (TASK-364).
    Fail-open: missing/unreadable intake leaves the prompt untouched."""
    try:
        intake = Path(cwd) / "docs" / "_meta" / "project-description.md"
        if not intake.is_file():
            return system_prompt
        text = intake.read_text(encoding="utf-8").strip()[:2000]
        if not text or not isinstance(system_prompt, dict) or "append" not in system_prompt:
            return system_prompt
        return {
            **system_prompt,
            "append": system_prompt["append"]
            + "\n\n## Project context (onboarding intake)\n"
            + text,
        }
    except OSError:
        return system_prompt


def _chat_system_prompt(model: str | None) -> dict:
    """claude_code preset + the chat framing, pinning the model name when known."""
    append = _CHAT_SYSTEM
    if model:
        append = (
            f"{_CHAT_SYSTEM}\n\nYou are answering as the `{model}` model. If the user "
            f"asks which model you are, tell them exactly `{model}`."
        )
    return {"type": "preset", "preset": "claude_code", "append": append}
