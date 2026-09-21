"""Encoder: availability detection, model loading, and text to vector.

Private module of embeddings.py — import through that facade.
"""

from __future__ import annotations

import functools
import os
from typing import Any

# Loaded flat as `embeddings` by thinking_os and as `thinking_os.embeddings`
# by graph_os; the relative form has no parent package under the first.
try:
    from ._embeddings_registry import (
        active_model_name,
        logger,
    )
except ImportError:  # pragma: no cover
    from _embeddings_registry import (  # type: ignore[no-redef]
        active_model_name,
        logger,
    )

# ---------------------------------------------------------------------------
# Availability detection — graceful degradation entry point
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def is_available() -> bool:
    """Return True iff sentence-transformers and numpy are importable.

    Result is cached for the process lifetime — checking is cheap after the
    first call.

    Returns:
        True if both `sentence_transformers` and `numpy` import successfully.
        False otherwise — callers must handle this and fall back.
    """
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


@functools.lru_cache(maxsize=4)
def _get_model_by_name(name: str) -> Any:
    """Load and cache an embedding model by name."""
    if not is_available():
        return None
    override = _MODEL_OVERRIDES.get(name)
    if override is not None:
        return override
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", name)
        return SentenceTransformer(name)
    except Exception as exc:
        if os.environ.get("COS_ALLOW_MODEL_DOWNLOAD") != "1":
            logger.warning(
                "Embedding model %s not in local cache; runtime downloads are "
                "disabled — set COS_ALLOW_MODEL_DOWNLOAD=1 once to vendor it. "
                "Falling back to lexical search. (%s)",
                name,
                exc,
            )
        else:
            logger.warning("Failed to load embedding model %s: %s", name, exc)
        return None


# Test hook: a mapping of model_name → pre-built encoder (duck-typed to
# expose .encode(...) with the sentence-transformers signature). Lets the
# test suite exercise dual-model behaviour without downloading BGE-M3.
_MODEL_OVERRIDES: dict[str, Any] = {}


def _override_model(name: str, encoder: Any) -> None:
    """Test-only: install a fake encoder for the given model name."""
    if encoder is None:
        _MODEL_OVERRIDES.pop(name, None)
    else:
        _MODEL_OVERRIDES[name] = encoder
    _get_model_by_name.cache_clear()
    _get_model.cache_clear()


@functools.lru_cache(maxsize=1)
def _get_model() -> Any:
    """Legacy shim — returns the active-model encoder.

    Kept as an lru_cache'd function so existing tests that call
    `_get_model.cache_clear()` continue to work after the
    refactor. Defers to the multi-model loader.
    """
    return _get_model_by_name(active_model_name())


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


def embed_text(text: str, model_name: str | None = None) -> bytes | None:
    """Embed a single text string with the active (or explicit) model."""
    if not text or not text.strip():
        return None
    # When the caller doesn't pick a model, route through the legacy
    # _get_model() so existing tests that patch it keep working.
    if model_name is None:
        model = _get_model()
        name = active_model_name()
    else:
        name = model_name
        model = _get_model_by_name(name)
    if model is None:
        return None
    try:
        import numpy as np

        vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32).tobytes()
    except Exception as exc:
        logger.warning("embed_text(%s) failed: %s", name, exc)
        return None


def embed_texts(texts: list[str], model_name: str | None = None) -> list[bytes | None]:
    """Batch-embed with the active (or explicit) model."""
    if not texts:
        return []
    if model_name is None:
        model = _get_model()
        name = active_model_name()
    else:
        name = model_name
        model = _get_model_by_name(name)
    if model is None:
        return [None] * len(texts)
    try:
        import numpy as np

        indices = [i for i, t in enumerate(texts) if t and t.strip()]
        valid_texts = [texts[i] for i in indices]
        if not valid_texts:
            return [None] * len(texts)
        vectors = model.encode(
            valid_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
        )
        results: list[bytes | None] = [None] * len(texts)
        for idx, vec in zip(indices, vectors, strict=False):
            results[idx] = np.asarray(vec, dtype=np.float32).tobytes()
        return results
    except Exception as exc:
        logger.warning("embed_texts(%s) failed: %s", name, exc)
        return [None] * len(texts)
