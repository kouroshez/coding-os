"""The duplicate-code ratchet fails on a new or grown clone group and only ever shrinks.

Spec: docs/engineering/graph_os-queries.md § Duplicate ratchet.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "src/core/scripts/check_graph_duplicates.py"


def _groups(*sizes: tuple[str, int]) -> list[dict]:
    return [
        {"fingerprint": fp, "members": [{"uid": f"code:function:{fp}.py::f{i}"} for i in range(n)]}
        for fp, n in sizes
    ]


def _run(tmp_path: Path, groups: list[dict], *args: str, fingerprinted: int = 100):
    envelope = {
        "ok": True,
        "data": {
            "groups": groups,
            "total_count": len(groups),
            "meta": {"fingerprinted_symbols": fingerprinted},
        },
    }
    (tmp_path / "dupes.json").write_text(json.dumps(envelope), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_cos = bin_dir / "cos"
    fake_cos.write_text(f'#!/bin/sh\ncat "{tmp_path / "dupes.json"}"\n', encoding="utf-8")
    fake_cos.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    baseline = tmp_path / "baseline.json"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--baseline", str(baseline), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )


def test_a_new_clone_group_fails(tmp_path: Path) -> None:
    assert _run(tmp_path, _groups(("aaa", 2)), "--update").returncode == 0

    proc = _run(tmp_path, _groups(("aaa", 2), ("bbb", 2)))

    assert proc.returncode == 1
    assert "[FAIL]" in proc.stdout and "bbb.py" in proc.stdout


def test_a_further_copy_of_a_known_group_fails(tmp_path: Path) -> None:
    _run(tmp_path, _groups(("aaa", 2)), "--update")

    proc = _run(tmp_path, _groups(("aaa", 3)))

    assert proc.returncode == 1
    assert "grew 2 -> 3" in proc.stdout


def test_update_shrinks_but_never_grows(tmp_path: Path) -> None:
    _run(tmp_path, _groups(("aaa", 2), ("bbb", 3)), "--update")

    assert _run(tmp_path, _groups(("aaa", 2), ("ccc", 2)), "--update").returncode == 1
    assert _run(tmp_path, _groups(("bbb", 2)), "--update").returncode == 0
    recorded = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    assert recorded == {"bbb": {"members": 2, "example": "code:function:bbb.py::f0"}}


def test_no_graph_index_is_a_skip_not_a_pass(tmp_path: Path) -> None:
    proc = _run(tmp_path, [], fingerprinted=0)

    assert proc.returncode == 0
    assert proc.stdout.startswith("[SKIP]")
