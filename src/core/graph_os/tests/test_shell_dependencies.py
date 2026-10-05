"""Shell scripts reach the libraries they source, the helpers they run and the functions they call."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_bash")

FILES = {
    "hooks/env.sh": (
        "#!/usr/bin/env bash\n"
        '_src="${BASH_SOURCE[0]}"\n'
        '_dir="$(cd -P "$(dirname "$_src")" && pwd)"\n'
        "for _part in _log _io; do\n"
        '  source "${_dir}/${_part}.sh"\n'
        "done\n"
    ),
    "hooks/_log.sh": "log_event() {\n  printf '%s\\n' \"$1\"\n}\n",
    "hooks/_io.sh": "read_input() {\n  cat\n}\n",
    "hooks/_helpers/check.py": "print('ok')\n",
    "scripts/report.py": "print('report')\n",
    "hooks/guard.sh": (
        "#!/usr/bin/env bash\n"
        'source "$(dirname "$0")/env.sh"\n'
        "if ! command -v log_event >/dev/null 2>&1; then log_event() { :; }; fi\n"
        'HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'PY="${COS_PYTHON:-python3}"\n'
        "main() {\n"
        "  log_event start\n"
        '  INPUT="$(read_input)"\n'
        '  "$PY" "$HOOK_DIR/_helpers/check.py"\n'
        "  uv run --extra graph python scripts/report.py\n"
        '  bash "$(dirname "$0")/_log.sh" extra.sh\n'
        "  jq -r '.x' <<<\"$INPUT\"\n"
        "  echo done\n"
        "  source /etc/profile\n"
        "  source scripts/missing.sh\n"
        "}\n"
        'main "$@"\n'
    ),
}


@pytest.fixture()
def graph(tmp_path: Path) -> str:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in FILES:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    return db


def _edges(db: str) -> set[tuple[str, str, str]]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id"
        ).fetchall()
    finally:
        conn.close()
    return {tuple(row) for row in rows}


def test_a_library_loop_with_a_script_dir_variable_sources_every_part(graph):
    edges = _edges(graph)
    assert ("code:module:hooks/env.sh", "imports", "code:file:hooks/_log.sh") in edges
    assert ("code:module:hooks/env.sh", "imports", "code:file:hooks/_io.sh") in edges


def test_helpers_run_through_variables_and_runners_are_edges(graph):
    edges = _edges(graph)
    main = "code:function:hooks/guard.sh::main"
    assert (main, "calls", "code:file:hooks/_helpers/check.py") in edges
    assert (main, "calls", "code:file:scripts/report.py") in edges
    assert (main, "calls", "code:file:hooks/_log.sh") in edges
    assert (main, "calls", "code:file:hooks/extra.sh") not in edges


def test_library_functions_bind_past_the_fallback_shim(graph):
    edges = _edges(graph)
    main = "code:function:hooks/guard.sh::main"
    assert (main, "calls", "code:function:hooks/_log.sh::log_event") in edges
    assert (main, "calls", "code:function:hooks/_io.sh::read_input") in edges
    assert (main, "calls", "code:function:hooks/guard.sh::log_event") not in edges


def test_builtins_mint_nothing_and_tools_stay_stubs(graph):
    targets = {target for _, _, target in _edges(graph)}
    assert "code:external:shfn:echo" not in targets
    assert "code:external:shfn:jq" in targets


def test_paths_outside_the_repo_or_missing_mint_no_phantom_file(graph):
    targets = {target for _, _, target in _edges(graph)}
    assert not any(target.endswith("etc/profile") for target in targets)
    assert not any("missing.sh" in target for target in targets)


def test_a_helper_named_through_a_variable_chain_is_an_edge(tmp_path):
    from graph_os.extractors import code_shell

    script = (
        '_src="${BASH_SOURCE[0]}"\n'
        'HSRC="$(cd -P "$(dirname "$_src")" && pwd)"\n'
        'HELPER="${HSRC}/_helpers/advance.py"\n'
        'CHOSEN=$(python3 "$HELPER" "$TOOL" 2>/dev/null || true)\n'
    )
    edges = {(e.edge_type, e.target_uid) for e in code_shell.extract("hooks/run.sh", script).edges}

    assert ("calls", "code:file:hooks/_helpers/advance.py") in edges
