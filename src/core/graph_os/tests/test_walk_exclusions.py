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
