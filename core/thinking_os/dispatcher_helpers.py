"""
Coding OS — Dispatcher shared helpers.

PURPOSE:      Helpers every adapter dispatcher needs but that are NOT
              agent-specific: parsing the formula agent file (frontmatter +
              body) and extracting the EvidenceBundle JSON block from a
              free-form transcript. Lives in core/ so adapters do not
              re-implement the same parsing logic and silently diverge.
INPUT:        Path strings, raw transcript strings.
OUTPUT:       Tuple[str, dict] for prompts; dict for JSON extraction.
DEPENDENCIES: pyyaml (optional); stdlib only otherwise. Adapter modules
              import these instead of duplicating private `_load_agent_prompt`
              / `_extract_json_block`.
NOTES:        Rule 1: stays agent-agnostic. Public surface is small on purpose
              — anything Claude- or Codex-specific belongs in adapters/.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("coding_os.dispatcher.helpers")

_CORE_TOS = Path(__file__).resolve().parent

_FENCED_JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", re.DOTALL)


def load_agent_prompt(agent_file: str) -> tuple[str, dict[str, Any]]:
    """
    PURPOSE: Read F<N>_<name>.md, split YAML frontmatter from body, return
             (body, frontmatter_dict). Relative paths resolve against
             core/thinking_os/ so adapters can pass `agents/F1_researcher.md`.
    INPUT:   absolute or repo-relative path to the agent .md file.
    OUTPUT:  (prompt_body, frontmatter) — frontmatter is {} when missing or
             when pyyaml is not importable.
    """
    path = Path(agent_file)
    if not path.is_absolute():
        path = _CORE_TOS / agent_file.lstrip("/")
    if not path.exists():
        raise FileNotFoundError(f"agent file not found: {agent_file}")

    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml  # local import — pyaml is a soft dep here
                meta = yaml.safe_load(parts[1]) or {}
            except ImportError:
                meta = {}
            return parts[2].strip(), meta
    return text.strip(), {}


def extract_json_block(transcript: str) -> dict[str, Any]:
    """
    PURPOSE: Pull the first ```json ... ``` block from a transcript and parse
             it. Falls back to a bare JSON object scan as a last resort.
    INPUT:   raw transcript text emitted by a formula agent.
    OUTPUT:  parsed dict, or {} if nothing parseable was found. Caller treats
             {} as a validation error — never raises.
    """
    m = _FENCED_JSON.search(transcript) or _BARE_JSON.search(transcript)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.debug("dispatcher JSON parse failed: %s", exc)
        return {}
