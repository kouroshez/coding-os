"""A consumer's .git/hooks/pre-commit is a stub that runs the installed body."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cli._init_git import install_consumer_git_hooks, replace_frozen_pre_commit

_SRC = Path(__file__).resolve().parent.parent / "src"
_STUB = _SRC / "scripts" / "_pre_commit_stub.sh"
_BODY = _SRC / "scripts" / "_pre_commit_body.sh"
_SHIM = _SRC / "core" / "scripts" / "hook-shim.sh"


def _consumer(tmp_path: Path, core_root: Path | None) -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    state = repo / ".coding-os"
    state.mkdir()
    shutil.copy2(_SHIM, state / "hook-shim.sh")
    if core_root is not None:
        (state / ".core-root").write_text(f"{core_root}\n", encoding="utf-8")
    (repo / "notes.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.txt"], cwd=repo, check=True)
    return repo


def _run_stub(repo: Path) -> subprocess.CompletedProcess[str]:
    # Files, not pipes: the body's reap-timeout watchdog leaves a sleep holding
    # its stdout, so a pipe reader would wait for that sleep to end.
    out, err = repo.parent / "stub.out", repo.parent / "stub.err"
    with out.open("w") as stdout, err.open("w") as stderr:
        proc = subprocess.run(
            ["bash", str(_STUB)], cwd=repo, stdout=stdout, stderr=stderr, timeout=60
        )
    return subprocess.CompletedProcess(proc.args, proc.returncode, out.read_text(), err.read_text())


def test_stub_runs_the_installed_body_and_its_scan(tmp_path: Path) -> None:
    proc = _run_stub(_consumer(tmp_path, _SRC))
    assert proc.returncode == 0, proc.stderr
    assert "cos pre-commit: OK" in proc.stdout
    assert "missing" not in proc.stderr


def test_stub_blocks_without_an_install(tmp_path: Path) -> None:
    repo = _consumer(tmp_path, None)
    (repo / ".coding-os" / "hook-shim.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    proc = _run_stub(repo)
    assert proc.returncode == 1
    assert "BLOCKED" in proc.stderr and "cos update" in proc.stderr


def test_body_blocks_when_its_scan_helper_is_missing(tmp_path: Path) -> None:
    bare_install = tmp_path / "install"
    (bare_install / "core" / "hooks").mkdir(parents=True)
    (bare_install / "scripts").mkdir()
    shutil.copy2(_BODY, bare_install / "scripts" / _BODY.name)
    proc = _run_stub(_consumer(tmp_path, bare_install))
    assert proc.returncode == 1
    assert "BLOCKED" in proc.stderr and "pre_commit_batch.py" in proc.stderr


def test_init_installs_the_stub(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    result = install_consumer_git_hooks(tmp_path, enabled=True)
    assert "pre-commit" in result.installed
    assert (tmp_path / ".git/hooks/pre-commit").read_bytes() == _STUB.read_bytes()


def test_update_replaces_only_a_frozen_body_copy(tmp_path: Path) -> None:
    repo = _consumer(tmp_path, _SRC)
    hook = repo / ".git/hooks/pre-commit"
    shutil.copy2(_BODY, hook)
    assert replace_frozen_pre_commit(repo) is True
    assert hook.read_bytes() == _STUB.read_bytes()
    assert replace_frozen_pre_commit(repo) is False

    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert replace_frozen_pre_commit(repo) is False
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_update_keeps_the_copy_where_no_shim_exists(tmp_path: Path) -> None:
    repo = _consumer(tmp_path, _SRC)
    (repo / ".coding-os" / "hook-shim.sh").unlink()
    hook = repo / ".git/hooks/pre-commit"
    shutil.copy2(_BODY, hook)
    assert replace_frozen_pre_commit(repo) is False
    assert hook.read_bytes() == _BODY.read_bytes()
