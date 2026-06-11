"""graph_os extractors.

Each module under this package turns a single source type (markdown
doc, task file, Python module, TS file, shell script, contracts ...)
into a stream of GraphNode + GraphEdge values that flows into the
shared GraphBackend. Extractors MUST be pure: no DB writes, no
sys.path tweaks, no network. The orchestrator owns the write path.
"""

from importlib import import_module
from pkgutil import iter_modules


def registered_extractor_ids() -> frozenset[str]:
    """EXTRACTOR_IDs of every importable extractor module; empty when any import fails (callers treat empty as 'registry unknown', never as 'all ids legacy')."""
    ids: set[str] = set()
    for info in iter_modules(__path__):
        try:
            module = import_module(f"{__name__}.{info.name}")
        except Exception:
            return frozenset()
        extractor_id = getattr(module, "EXTRACTOR_ID", None)
        if isinstance(extractor_id, str):
            ids.add(extractor_id)
    return frozenset(ids)
