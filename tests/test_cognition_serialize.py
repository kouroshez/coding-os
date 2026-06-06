"""_safe_serialize must stamp `type` on blocks nested in a streamed message (TASK-207).

The agent-draft / new-chat SSE stream serializes SDK dataclass events. The old
implementation used dataclasses.asdict, which pre-flattened the whole tree so a
nested TextBlock arrived as a plain dict and never got its `type` — the UI then
dropped every block and the modal showed nothing. These local dataclasses mimic
the SDK shape (class names match _BLOCK_TYPE_BY_CLASS) without requiring the SDK.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes.cognition import _safe_serialize


@dataclasses.dataclass
class TextBlock:
    text: str


@dataclasses.dataclass
class AssistantMessage:
    content: list


def test_nested_block_keeps_type():
    out = _safe_serialize(AssistantMessage(content=[TextBlock("hi")]))
    assert out["content"][0] == {"text": "hi", "type": "text"}


def test_top_level_block_keeps_type():
    assert _safe_serialize(TextBlock("yo")) == {"text": "yo", "type": "text"}
