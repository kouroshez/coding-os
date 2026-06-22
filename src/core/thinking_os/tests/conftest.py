"""thinking_os test fixtures.

Puts core/thinking_os on sys.path so tests using bare imports
(``from cognition import ...``, ``from database import ...``) resolve the
same way the MCP server does at runtime. Without this conftest,
``pytest core/thinking_os/tests/`` collects but cannot import these
modules and aborts with ModuleNotFoundError. Mirrors the pattern in
core/graph_os/tests/conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THINKING_OS_DIR = Path(__file__).resolve().parent.parent

if str(_THINKING_OS_DIR) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR))
if str(_THINKING_OS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR.parent))


@pytest.fixture(autouse=True)
def _isolate_durable_log_db(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect the durable log DB so test-deliberate errors never persist.

    Importing thinking_os.server installs the logging_os stdlib bridge
    process-globally, so every logger.error/.warning from production code under
    test routes to the durable log_events store at COS_DB_PATH. The error-path
    fixtures here (test_envelope.py's cos_fake_unshrinkable, embed_text with a
    bogus model) log on purpose; without this redirect those land in the real
    .coding-os/coding-os.db and the nightly error-sweep files them as phantom
    bug tasks (TASK-243/244). Tests that need a real DB set their own
    COS_DB_PATH after this autouse fixture, so last-write-wins keeps them green.
    """
    tmp_root = tmp_path_factory.mktemp("log_isolate", numbered=True)
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_root / ".coding-os"))
    monkeypatch.setenv("COS_DB_PATH", str(tmp_root / ".coding-os" / "coding-os.db"))


class _StubEncoder:
    """Deterministic token-hash encoder — keeps coarse cosine ranking
    (shared tokens → higher similarity) without loading torch/MiniLM."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def encode(self, texts, **_kwargs):
        import zlib

        import numpy as np

        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        out = []
        for text in items:
            vec = np.zeros(self.dim, dtype=np.float32)
            for token in str(text).lower().split():
                vec[zlib.crc32(token.encode("utf-8")) % self.dim] += 1.0
            norm = float(np.linalg.norm(vec))
            if norm:
                vec /= norm
            out.append(vec)
        return out[0] if single else np.stack(out)


@pytest.fixture(autouse=True)
def _stub_embedding_models(request: pytest.FixtureRequest):
    """Replace SentenceTransformer loads with a cheap deterministic stub.

    The real model import chain (torch + sentence-transformers) costs seconds
    of load and hundreds of MB RSS per pytest process — multiplied across
    concurrent agent sessions (TASK-331, docs/engineering/test-governance.md).
    Tests that assert true semantic behaviour (synonyms, near-duplicate
    consolidation) opt out with @pytest.mark.real_embeddings; set
    COS_TEST_REAL_EMBEDDINGS=1 to exercise the real models everywhere.
    """
    import os as _os

    if (
        _os.environ.get("COS_TEST_REAL_EMBEDDINGS") == "1"
        or request.node.get_closest_marker("real_embeddings") is not None
    ):
        import embeddings

        # real_embeddings tests need the actual model weights, not just the
        # sentence-transformers package (REQUIRES_RAG only checks the package).
        # CI runs offline (HF_HUB_OFFLINE) with no vendored model, so the load
        # returns None — skip rather than fail with empty-result assertions.
        if embeddings._get_model() is None:
            pytest.skip(
                "real embedding model unavailable (offline / not vendored) — "
                "set COS_ALLOW_MODEL_DOWNLOAD=1 to vendor it"
            )
        yield
        return
    import embeddings

    names = set(embeddings.MODEL_DIMS) | {embeddings.active_model_name()}
    for name in names:
        dim = embeddings.MODEL_DIMS.get(name, embeddings.EMBEDDING_DIM)
        embeddings._override_model(name, _StubEncoder(dim))
    yield
    for name in names:
        embeddings._override_model(name, None)
