"""B14 contract test — edge_types emitted by contracts.py match cos_graph_contracts."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure graph_os + thinking_os are importable.
_GRAPH_OS_DIR = Path(__file__).resolve().parent.parent
_THINKING_OS_DIR = _GRAPH_OS_DIR.parent / "thinking_os"
for _p in (_THINKING_OS_DIR, _GRAPH_OS_DIR.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Edge types declared in the extractor
# ---------------------------------------------------------------------------


def _extractor_edge_types() -> set[str]:
    """Collect every edge_type value that contracts.py can emit.

    The ``_emit`` function uses a dict mapping ContractMatch.kind to
    edge_type strings. We read that dict directly from the module so
    this test stays in sync without parsing source.
    """
    from graph_os.extractors.contracts import ContractMatch, _emit  # type: ignore

    # ContractMatch.kind values from the extractor source.
    all_kinds = ("http", "mcp", "grpc", "event", "websocket")

    # Replay _emit's internal mapping by inspecting the edge_type lookup
    # table embedded in it. Rather than exec-ing source, we call _emit
    # with synthetic ContractMatch objects and capture the edge_type from
    # the emitted edges.
    from graph_os.extractors.md_links import ExtractionResult  # type: ignore

    # Minimal file node to satisfy _emit's source_uid.
    dummy_file_uid = "code:file:test_contracts_dummy.py"

    edge_types: set[str] = set()
    for kind in all_kinds:
        match = ContractMatch(
            kind=kind,
            framework="test",
            method="get",
            path="/test",
            handler=None,
            line=1,
        )
        result = ExtractionResult()
        # _emit appends to result.edges.
        _emit(dummy_file_uid, match, normalised="test_contracts_dummy.py", result=result)
        for edge in result.edges:
            # Only include edges emitted from the file node (not handler stubs).
            if edge.source_uid == dummy_file_uid:
                edge_types.add(edge.edge_type)
    return edge_types


# ---------------------------------------------------------------------------
# Edge types expected by cos_graph_contracts
# ---------------------------------------------------------------------------


def _tool_expected_edge_types() -> set[str]:
    from graph_os.tools._analysis_contracts import _CONTRACT_EDGE_TYPES  # type: ignore

    return set(_CONTRACT_EDGE_TYPES)


# ---------------------------------------------------------------------------
# Test assertions
# ---------------------------------------------------------------------------


def test_extractor_edge_types_covered_by_tool():
    """Every edge_type emitted by contracts.py must appear in cos_graph_contracts' edge types."""
    extractor_types = _extractor_edge_types()
    tool_types = _tool_expected_edge_types()

    missing_from_tool = extractor_types - tool_types
    assert not missing_from_tool, (
        f"contracts.py emits edge_type(s) not queried by cos_graph_contracts: "
        f"{missing_from_tool!r}. Add them to `_CONTRACT_EDGE_TYPES`."
    )


def test_tool_edge_types_covered_by_extractor():
    """Every edge_type queried by cos_graph_contracts must be emittable by contracts.py."""
    extractor_types = _extractor_edge_types()
    tool_types = _tool_expected_edge_types()

    missing_from_extractor = tool_types - extractor_types
    assert not missing_from_extractor, (
        f"cos_graph_contracts queries edge_type(s) never emitted by contracts.py: "
        f"{missing_from_extractor!r}. Either add emitters or remove them from `_CONTRACT_EDGE_TYPES`."
    )
