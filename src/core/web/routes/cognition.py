"""core.web.routes.cognition — /api/cognition/* HTTP wrappers.

Module layout:
  _cognition_base           the shared APIRouter + state/db/module accessors
  cognition_chat            the Claude Agent SDK transcript browser + resume
  cognition_onboarding      the docs-scoped onboarding session

The sibling route groups reach the shared accessors through THIS module object
(`from . import cognition as _cog`), so a test that patches `cognition._db_path`
still reaches them. That is why the names below are re-exported rather than
called only where they are defined.
"""

from __future__ import annotations

# Import-for-side-effect: the chat and onboarding routes decorate the shared
# `router`, so importing this module registers every /api/cognition path.
from . import (
    cognition_chat,  # noqa: F401
    cognition_onboarding,  # noqa: F401
)
from ._cognition_base import (
    _CORE_DIR as _CORE_DIR,
    _auto_route_model as _auto_route_model,
    _cognition_module as _cognition_module,
    _db_path as _db_path,
    _state_dir as _state_dir,
    _unavailable as _unavailable,
    router as router,
)
from ._cognition_serialize import _sse_chunk
from .cognition_chat import (
    _dispatch_transcript_chat,
    _prime_with_project_description,
    _role_names,
    _role_system_prompt,
    _safe_serialize,
)
from .cognition_onboarding import _onboard_write_allowed, _onboarding_state

__all__ = [
    "_dispatch_transcript_chat",
    "_onboard_write_allowed",
    "_onboarding_state",
    "_prime_with_project_description",
    "_role_names",
    "_role_system_prompt",
    "_safe_serialize",
    "_sse_chunk",
    "router",
]
