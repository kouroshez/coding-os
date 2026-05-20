"""Coding OS — Dispatcher shared helpers."""

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
    m = _FENCED_JSON.search(transcript) or _BARE_JSON.search(transcript)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.debug("dispatcher JSON parse failed: %s", exc)
        return {}
