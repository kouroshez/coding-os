"""Lockfiles, COS_GRAPH_EXCLUDE_PATHS and .gitignore keep files out of both index paths."""

from __future__ import annotations

from pathlib import Path

from graph_os.ingest.base import walk_local


def _touch(root: Path, relative: str, text: str = "{}\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _walked(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in walk_local(root).files}


def test_lockfiles_are_not_walked(tmp_path):
    for name in ("package.json", "pnpm-lock.yaml", "package-lock.json", "app/config.yaml"):
        _touch(tmp_path, name)

    assert _walked(tmp_path) == {"package.json", "app/config.yaml"}


def test_env_extra_paths_exclude_directories_and_single_files(tmp_path, monkeypatch):
    for name in ("gen/api.ts", "spec/openapi.yaml", "spec/notes.yaml", "src/main.ts"):
        _touch(tmp_path, name)
    monkeypatch.setenv("COS_GRAPH_EXCLUDE_PATHS", "gen, spec/openapi.yaml")

    assert _walked(tmp_path) == {"spec/notes.yaml", "src/main.ts"}


def test_single_file_reindex_skips_what_the_walk_skips(tmp_path):
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    _touch(tmp_path, ".gitignore", "scratch/\n")
    db = str(tmp_path / "graph.db")
    for relative in ("pnpm-lock.yaml", "scratch/tmp.ts"):
        report = dispatch(
            _touch(tmp_path, relative, "export const x = 1;\n"),
            project_root=tmp_path,
            db_path=db,
        )
        assert report["status"] == "skipped", relative


def test_project_tooling_under_agents_is_walked_but_agent_memory_is_not(tmp_path):
    for name in (".agents/hooks/guard.sh", ".agents/memory/MEMORY.md", ".claude/settings.json"):
        _touch(tmp_path, name, "#!/usr/bin/env bash\n")

    assert _walked(tmp_path) == {".agents/hooks/guard.sh"}


def test_a_file_outside_the_include_list_is_not_walked(tmp_path):
    for name in ("src/app.ts", "assets/site.css", "assets/icon.svg", "notes.txt", "Makefile"):
        _touch(tmp_path, name)
    _touch(tmp_path, "bin/deploy", "#!/usr/bin/env bash\necho hi\n")

    assert _walked(tmp_path) == {"src/app.ts", "bin/deploy"}


def test_a_build_named_folder_git_tracks_is_source_and_an_untracked_one_is_not(tmp_path):
    import subprocess

    from graph_os.ingest.base import is_excluded

    tracked = ("internal/build/version.go", "internal/target/pick.go", "src/dist/math.ts")
    for name in (*tracked, "vendor/lib/lib.go", "dist/bundle.js", "build/out.py", "main.go"):
        _touch(tmp_path, name, "package x\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", *tracked, "vendor", "main.go"], cwd=tmp_path, check=True)

    assert _walked(tmp_path) == {*tracked, "main.go"}
    assert not is_excluded("internal/build/version.go", root=tmp_path)
    assert is_excluded("dist/bundle.js", root=tmp_path)
    assert is_excluded("vendor/lib/lib.go", root=tmp_path)
    assert is_excluded("internal/build/version.go")
