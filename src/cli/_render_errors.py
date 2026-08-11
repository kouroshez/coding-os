"""The single error every renderer raises.

Its own module so the fragment renderer, the settings renderer, and any future
one can all raise it without one of them owning the others' import.
"""

from __future__ import annotations


class RenderError(RuntimeError):
    """Raised when a fragment fails to render."""
