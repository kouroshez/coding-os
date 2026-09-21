"""Model registry: which model is active, its dimensions, and its floors.

Private module of embeddings.py — import through that facade.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

# Streaming batch sizes — bound peak memory regardless of table size.
# search streams candidate vectors; reindex streams + batch-embeds source rows.
_SEARCH_BATCH = 4096
_REINDEX_BATCH = 64


logger = logging.getLogger("coding_os.embeddings")

# Enterprise: never make unauthenticated HuggingFace Hub requests at runtime.
# Default to offline (use the locally-cached model only). A first-time vendoring
# download is explicit opt-in via COS_ALLOW_MODEL_DOWNLOAD=1, so the agent
# runtime never phones home without consent. setdefault respects an operator's
# own HF_HUB_OFFLINE choice.
if os.environ.get("COS_ALLOW_MODEL_DOWNLOAD") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Default model for FRESH projects — BAAI/bge-m3: 1024-dim, multilingual,
# ~4.3GB first-time download (vendored explicitly via COS_ALLOW_MODEL_DOWNLOAD=1).
# Per-project opt-back to MiniLM via COS_EMBEDDING_MODEL. The model a running
# process actually encodes with is active_model_name(), NOT this constant.
DEFAULT_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 384  # Legacy MiniLM dim — last-resort fallback; per-model dims live in MODEL_DIMS
EMBEDDING_BYTES = EMBEDDING_DIM * 4  # float32 → 4 bytes per dimension

# Dual-model support during the MiniLM → BGE-M3 migration.
# Each entry: output dim per model. Callers can opt into BGE-M3 via the
# COS_EMBEDDING_MODEL env var or an explicit model_name kwarg. The DB
# remembers the model_name + embedding_dim per row so mixed populations
# are queryable through dim-aware cosine_similarity.
MODEL_DIMS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "BAAI/bge-m3": 1024,
}

# Source tables that support embedded retrieval. New tables can be added
# without code changes — just call upsert_embedding with the new table name.
DEFAULT_SOURCE_TABLES = (
    "observations",
    "learned_patterns",
    "outcome_history",
    "document_chunks",
    "tasks",
)

# graph_node kinds worth embedding for semantic code search. Identifiers,
# imports, and external stubs are excluded — they are similarity noise (G21)
# and carry no meaningful label+signature+docstring text. Stored kinds are
# the canonical short forms (migration v16); see graph_os.types.NodeKind.
GRAPH_EMBED_KINDS: tuple[str, ...] = (
    "function",
    "method",
    "class",
    "route",
    "mcp_tool",
    "doc_heading",
)


def _active_model_marker_path() -> Path:
    from pathlib import Path

    state = os.environ.get("COS_STATE_DIR") or str(
        Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())) / ".coding-os"
    )
    return Path(state) / ".embedding-model"


def active_model_name() -> str:
    """Return the model the current process encodes with.

    SSOT order (M5): COS_EMBEDDING_MODEL env > persisted cutover marker
    (.coding-os/.embedding-model) > DEFAULT_MODEL_NAME. The marker lets the
    cutover flip every process to the new model at once after the corpus is
    fully re-embedded, instead of each process guessing from its own env.
    """
    env = os.environ.get("COS_EMBEDDING_MODEL", "").strip()
    if env:
        return env
    try:
        marker = _active_model_marker_path()
        if marker.exists():
            name = marker.read_text(encoding="utf-8").strip()
            if name in MODEL_DIMS:
                return name
    except OSError as exc:
        logger.debug("active-model marker read skipped: %s", exc)
    return DEFAULT_MODEL_NAME


def set_active_model(name: str) -> None:
    """Persist the active-model cutover marker (atomic tmp+replace)."""
    if name not in MODEL_DIMS:
        raise ValueError(f"unknown model {name!r}; known: {sorted(MODEL_DIMS)}")
    marker = _active_model_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(name, encoding="utf-8")
    tmp.replace(marker)


# Calibrated similarity floors per model (measured 2026-06: BGE-M3 separates
# related code-symbol cosine ~0.84 from unrelated ~0.55; MiniLM barely
# separates 0.39 vs 0.35). The persisted-vector similar path caps its floor at
# this value so a legacy confidence_min default cannot suppress the fast path.
_PERSISTED_FLOORS: dict[str, float] = {
    "all-MiniLM-L6-v2": 0.25,
    "BAAI/bge-m3": 0.60,
}


def persisted_similarity_floor(model_name: str | None = None) -> float:
    """Calibrated cosine floor for the persisted-embedding similar path."""
    return _PERSISTED_FLOORS.get(model_name or active_model_name(), 0.25)


# Calibrated cosine floors for DOC-CHUNK semantic search (cos_doc_search).
# Distinct from _PERSISTED_FLOORS: query-vs-doc-chunk cosines sit lower than
# code-symbol-vs-symbol ones, so the node floor (0.60) would discard genuine
# hits. Measured 2026-06 on the dogfood corpus: BGE-M3 related ~0.54-0.68 vs
# noise ~0.31-0.49 → 0.50 is the clean split. MiniLM keeps its legacy 0.05
# (it barely separates, so an aggressive floor just costs recall).
_DOC_FLOORS: dict[str, float] = {
    "all-MiniLM-L6-v2": 0.05,
    "BAAI/bge-m3": 0.50,
}


def doc_similarity_floor(model_name: str | None = None) -> float:
    """Calibrated cosine floor for cos_doc_search semantic ranking."""
    return _DOC_FLOORS.get(model_name or active_model_name(), 0.05)


# Calibrated cosine floor for AGENT-MEMORY semantic search (cos_search over
# observations + learned_patterns) and short task records. Measured 2026-07 on
# the dogfood corpus: genuine synonym matches on short memory text land ~0.50-0.62
# (a marketplace task at 0.51, a Celery obs at 0.50) while unrelated rows sit
# <=0.40 — so 0.45 clears real signal with margin below the lowest genuine hit
# and above the noise cluster. This floor is LOWER than doc chunks (0.50) and
# code symbols (0.60): short natural-language memory rows separate at lower
# cosines than either, so borrowing the code-symbol 0.55 (the prior value) just
# filtered genuine recall. MiniLM keeps its legacy 0.05 (it barely separates, so
# a hard floor only costs recall).
_MEMORY_FLOORS: dict[str, float] = {
    "all-MiniLM-L6-v2": 0.05,
    "BAAI/bge-m3": 0.45,
}


def memory_similarity_floor(model_name: str | None = None) -> float:
    """Calibrated cosine floor for agent-memory + task semantic search."""
    return _MEMORY_FLOORS.get(model_name or active_model_name(), 0.05)


def migration_status(conn: sqlite3.Connection, target_model: str | None = None) -> dict:
    """Report re-embedding progress toward target_model (cutover-gate input)."""
    target = target_model or active_model_name()
    try:
        total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        remaining = conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE model_name IS NULL OR model_name != ?",
            (target,),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return {"target": target, "total": 0, "remaining": 0, "complete": False}
    return {
        "target": target,
        "total": int(total),
        "remaining": int(remaining),
        "complete": total > 0 and remaining == 0,
    }


def model_dim(model_name: str) -> int | None:
    """Return the expected vector dim for a known model, else None."""
    return MODEL_DIMS.get(model_name)


def bytes_to_dim(payload: bytes | None) -> int | None:
    """Return dim inferred from a raw float32 blob (len / 4)."""
    if not payload:
        return None
    if len(payload) % 4 != 0:
        return None
    return len(payload) // 4
