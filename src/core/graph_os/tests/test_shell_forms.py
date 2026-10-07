"""The script-directory idioms and run forms real scripts use reach the file they name."""

from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("tree_sitter_bash")

LIB = "lib/common.sh"
SOURCES = {
    "cd_dashdash": (
        'SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )\n'
        'source "$SCRIPT_DIR/../lib/common.sh"\n'
    ),
    "cd_up": 'ROOT="$(cd "$(dirname "$0")/.." && pwd)"\nsource "$ROOT/lib/common.sh"\n',
    "readlink": 'source "$(dirname "$(readlink -f "$0")")/../lib/common.sh"\n',
    "realpath": (
        'HERE="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"\nsource "$HERE/../lib/common.sh"\n'
    ),
    "default": 'LIB_DIR="${LIB_DIR:-$(dirname "$0")/../lib}"\nsource "$LIB_DIR/common.sh"\n',
    "reassigned": 'DIR=/opt/elsewhere\nDIR="$(dirname "$0")/../lib"\nsource "$DIR/common.sh"\n',
    "backticks": 'DIR=`dirname $0`\nsource "$DIR/../lib/common.sh"\n',
}
RUNS = {
    "python_value_flag": ("python3 -W ignore tools/t.py", "tools/t.py"),
    "python_x_flag": ("python3 -X importtime tools/t.py", "tools/t.py"),
    "timeout_duration": ("timeout 5s python3 tools/t.py", "tools/t.py"),
    "uv_run_script": ("uv run tools/t.py", "tools/t.py"),
    "node_require": ("node --require ./tools/reg.js tools/m.mjs", "tools/m.mjs"),
    "bun_run": ("bun run tools/m.ts", "tools/m.ts"),
    "deno_run": ("deno run -A tools/m.ts", "tools/m.ts"),
    "pnpm_tsx": ("pnpm tsx tools/m.ts", "tools/m.ts"),
    "bash_extensionless": ("bash bin/tool", "bin/tool"),
    "path_extensionless": ('"$(dirname "$0")/../bin/tool" --flag', "bin/tool"),
    "sudo": ("sudo -u deploy bash scripts/other.sh", "scripts/other.sh"),
    "xargs": ("find . -name '*.txt' | xargs -n 1 bash scripts/other.sh", "scripts/other.sh"),
    "copy_variable": ("$COPY_CMD tools/t.py /tmp/", None),
}
FILES = {
    LIB: 'log_it() {\n  echo "$@"\n}\n',
    "tools/t.py": "print(1)\n",
    "tools/m.mjs": "1\n",
    "tools/m.ts": "1\n",
    "tools/reg.js": "1\n",
    "bin/tool": "#!/usr/bin/env bash\necho hi\n",
    "scripts/other.sh": "echo o\n",
    "scripts/probe.sh": (
        "#!/usr/bin/env bash\n"
        'source "$(dirname "$0")/../lib/common.sh"\n'
        "command -v log_it >/dev/null 2>&1 || echo missing\n"
    ),
    **{f"scripts/s_{name}.sh": "#!/usr/bin/env bash\n" + text for name, text in SOURCES.items()},
    **{
        f"scripts/r_{name}.sh": f"#!/usr/bin/env bash\n{command}\n"
        for name, (command, _) in RUNS.items()
    },
}


@pytest.fixture(scope="module")
def edges(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    root = tmp_path_factory.mktemp("shell_forms")
    (root / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(root / "graph.db")
    for relative in FILES:
        dispatch(root / relative, project_root=root, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.file_path, e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id"
        ).fetchall()
    finally:
        conn.close()
    return {tuple(row) for row in rows}


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_a_script_directory_idiom_sources_the_library(edges, name):
    assert (f"scripts/s_{name}.sh", "imports", f"code:file:{LIB}") in edges


@pytest.mark.parametrize("name", sorted(RUNS))
def test_a_run_form_reaches_the_file_it_runs(edges, name):
    script = f"scripts/r_{name}.sh"
    ran = {target for source, kind, target in edges if source == script and kind == "calls"}
    ran = {target.removeprefix("code:file:") for target in ran if target.startswith("code:file:")}
    expected = RUNS[name][1]

    assert expected in ran if expected else not ran


def test_command_v_looks_a_function_up_without_calling_it(edges):
    calls = {target for source, kind, target in edges if source == "scripts/probe.sh"}
    assert f"code:function:{LIB}::log_it" not in calls


def test_keywords_tree_sitter_cannot_parse_are_never_function_calls():
    from graph_os.extractors import code_shell

    script = (
        "hash_string() {\n"
        '  str="${1:-}" h=0\n'
        '  while [ -n "$str" ]; do\n'
        '    h=$(((h * 31 + $(LC_CTYPE=C printf %d "\'$char")) % 4294967296))\n'
        '    str="${str#?}"\n'
        "  done\n"
        "}\n"
    )
    targets = {edge.target_uid for edge in code_shell.extract("bin/mvnw", script).edges}

    assert not {"code:external:shfn:while", "code:external:shfn:do", "code:external:shfn:done"} & (
        targets
    )
