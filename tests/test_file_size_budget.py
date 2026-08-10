"""File-size ratchet: no tracked Python file may grow past its recorded size.

Two shrink-only gates, because a single global cap only ever watches the
one largest file — every other file could triple silently, which is exactly
how server.py reached 3,159 lines one accepted commit at a time:

* `SOFT_LIMIT` — a file absent from `BASELINE` must stay under it, so no
  NEW god-file can form.
* `BASELINE` — the files already over `SOFT_LIMIT` when this landed. Each
  may only shrink; splitting one means lowering its entry, and deleting the
  entry once the file drops under `SOFT_LIMIT`.

Raising a number (or adding a `BASELINE` key) is a review-rejected change by
policy: docs/engineering/ci-gates.md § File-size ratchet. Failures print the
exact replacement line so tightening is mechanical.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SOFT_LIMIT = 800

BASELINE: dict[str, int] = {
    "src/cli/main.py": 1601,
    # Append-only schema ledger — recorded exception, see ci-gates.md.
    "src/core/thinking_os/_db_migrations.py": 2316,
    "src/core/thinking_os/tools/learning.py": 1061,
    "src/core/thinking_os/tools/cognition.py": 1237,
    "src/cli/pr_commands.py": 2024,
    "tests/_cli_suite/pr.py": 2018,
    "src/core/graph_os/tools/graph.py": 1271,
    "src/core/graph_os/extractors/code_ts.py": 930,
    "src/core/thinking_os/tests/test_learning.py": 1598,
    "src/core/graph_os/extractors/contracts.py": 1196,
    "src/core/thinking_os/tests/test_db.py": 1538,
    "src/core/graph_os/extractors/code_python.py": 1454,
    "src/core/graph_os/extractors/code_go.py": 1422,
    "tests/test_hooks.py": 1287,
    "src/core/graph_os/tests/test_mcp_tools.py": 1274,
    "src/cli/graph_commands.py": 1264,
    "src/cli/board_commands.py": 1258,
    "src/core/graph_os/tools/_graph_read.py": 1256,
    "src/core/graph_os/tools/_graph_insights.py": 1248,
    "tests/_cli_suite/subsystems.py": 1243,
    "src/core/web/routes/hub.py": 1217,
    "src/core/graph_os/tests/test_polyglot_quality.py": 1153,
    "src/cli/doctor_extras.py": 1121,
    "tests/test_branch_guard.py": 1120,
    "tests/test_template_scaffold.py": 1117,
    "src/core/web/routes/board.py": 1086,
    "src/core/graph_os/backends/sqlite_backend.py": 1052,
    "src/core/graph_os/extractors/code_php.py": 979,
    "src/core/board_os/workflow.py": 964,
    "src/core/thinking_os/tools/_shared.py": 947,
    "src/core/thinking_os/embeddings.py": 943,
    "src/core/board_os/_mcp_reclaim.py": 935,
    "tests/_cli_suite/init_install.py": 932,
    "src/core/scheduled/nightly.py": 930,
    "src/core/graph_os/tests/test_centrality_ranking_doctor.py": 925,
    "src/adapters/claude/sdk_dispatcher.py": 920,
    "src/core/thinking_os/tests/test_dispatcher.py": 914,
    "src/core/graph_os/extractors/code_generic.py": 914,
    "src/core/thinking_os/doc_indexer.py": 905,
    "src/core/graph_os/extractors/md_links.py": 890,
    "src/core/thinking_os/tests/test_supervision.py": 868,
    "src/core/thinking_os/tools/memory.py": 839,
    "tests/test_hooks_phase_f.py": 837,
    "src/core/graph_os/tests/test_i7_extractors.py": 825,
    "src/core/thinking_os/tests/test_seed_simulation.py": 822,
}

EXCLUDED_PREFIXES = (
    "src/templates/",  # consumer-shipped scaffold; downstream owns style
    "tests/golden/",  # generated snapshots
    "archive/",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_line_counts() -> dict[str, int]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    counts: dict[str, int] = {}
    for rel in out.stdout.splitlines():
        if not rel or rel.startswith(EXCLUDED_PREFIXES):
            continue
        try:
            counts[rel] = sum(1 for _ in (REPO_ROOT / rel).open("rb"))
        except OSError:
            continue  # deleted-but-still-tracked mid-rebase; git owns it
    return counts


def test_no_python_file_exceeds_its_size_ratchet() -> None:
    grown: list[str] = []
    new_offenders: list[str] = []
    for rel, count in sorted(_tracked_line_counts().items()):
        recorded = BASELINE.get(rel)
        if recorded is None:
            if count > SOFT_LIMIT:
                new_offenders.append(f"  {rel}: {count} lines (> {SOFT_LIMIT})")
        elif count > recorded:
            grown.append(f'  "{rel}": {recorded} -> {count} (+{count - recorded})')

    message = ""
    if grown:
        message += (
            "These files grew past their recorded ratchet. Move the added code "
            "into a sibling module instead of raising the number:\n" + "\n".join(grown) + "\n"
        )
    if new_offenders:
        message += (
            f"These files crossed {SOFT_LIMIT} lines. Split them — do NOT add a "
            "BASELINE entry, which is reserved for debt that predates the gate:\n"
            + "\n".join(new_offenders)
            + "\n"
        )
    assert not message, message


def test_baseline_has_no_stale_entries() -> None:
    counts = _tracked_line_counts()
    stale: list[str] = []
    for rel, recorded in sorted(BASELINE.items()):
        count = counts.get(rel)
        if count is None:
            stale.append(f'  "{rel}": {recorded}  # file no longer tracked')
        elif count <= SOFT_LIMIT:
            stale.append(f'  "{rel}": {recorded}  # now {count} lines, under the limit')
    assert not stale, (
        "Delete these BASELINE entries — the ratchet only tightens when paid-off "
        "debt leaves the list:\n" + "\n".join(stale)
    )
