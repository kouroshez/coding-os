"""Graph-envelope token cost vs naive file-read baseline (TASK-483).

Wires src/core/graph_os/bench/token_cost.py into `make bench` / pytest -m
bench. Asserts only a gross-regression gate (graph envelope must not cost
more than 2x the naive read it replaces) — never tight per-workflow
thresholds, because the estimator is a chars/4 heuristic. The measured
numbers print as JSON so the doc bands can be refreshed from a real run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CORE = Path(__file__).resolve().parent.parent.parent / "src" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
if str(_CORE / "thinking_os") not in sys.path:
    sys.path.insert(0, str(_CORE / "thinking_os"))

pytestmark = pytest.mark.bench

# Heuristic graph-envelope token bands from a real run against the committed
# deterministic fixtures (chars/4 estimator). The CI gate trips ONLY on a
# >2x balloon of any envelope — never a tight threshold. Refresh by running
# `python -m graph_os.bench.token_cost` and copying graph_tokens.
_EXPECTED_GRAPH_TOKENS = {
    "references": 423,
    "rename_plan": 6580,
    "contracts": 3917,
    "communities+export": 97689,
    "detect_changes": 8238,
}


def test_token_cost_report(capsys):
    from graph_os.bench.token_cost import WORKFLOWS, measure_token_cost

    rows = measure_token_cost()
    assert {r.workflow for r in rows} == set(WORKFLOWS)

    with capsys.disabled():
        print("\n" + json.dumps([r.to_dict() for r in rows], indent=2))

    for row in rows:
        assert row.graph_tokens > 0, row.workflow
        assert row.naive_tokens > 0, row.workflow
        # Gross-regression gate only: the graph envelope must not balloon past
        # 2x its recorded band. Loose by design (chars/4 heuristic estimator).
        band = _EXPECTED_GRAPH_TOKENS[row.workflow]
        assert row.graph_tokens <= 2 * band, (
            f"{row.workflow}: graph envelope {row.graph_tokens} tokens > 2x band {band}"
        )
