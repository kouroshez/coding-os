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
    for name in ("src/app.ts", "src/Legacy.TS", "assets/site.css", "assets/icon.svg", "notes.txt"):
        _touch(tmp_path, name)
    _touch(tmp_path, "Makefile")
    _touch(tmp_path, "bin/deploy", "#!/usr/bin/env bash\necho hi\n")

    assert _walked(tmp_path) == {"src/app.ts", "src/Legacy.TS", "bin/deploy"}


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


def test_stack_build_and_cache_output_stays_out_without_a_gitignore(tmp_path):
    generated = (
        ".expo/types/router.ts",
        ".yarn/releases/yarn-4.cjs",
        "ios/DerivedData/Build/Bridge.h",
        "android/app/.cxx/Debug/x.cpp",
        "android/app/build/generated/R.java",
        ".dart_tool/package_config.json",
        "ios/Flutter/ephemeral/flutter_lldb.py",
        "coverage/lcov-report/sorter.js",
        "htmlcov/coverage_html.js",
        "storybook-static/main.js",
        ".angular/cache/x.js",
        ".tox/py312/lib/x.py",
        "out/_next/static/chunk.js",
        "venv/lib/python3.12/site-packages/pkg/mod.py",
        "env/bin/activate_this.py",
    )
    source = ("src/app.ts", "ios/App/Bridge.h", "android/app/src/main/Main.kt")
    for name in (*generated, *source):
        _touch(tmp_path, name)
    for venv in ("venv", "env"):
        _touch(tmp_path, f"{venv}/pyvenv.cfg", "home = /usr/bin\n")
    _touch(tmp_path, "android/gradlew", "#!/bin/sh\nmain() { :; }\n")
    _touch(tmp_path, "mvnw", "#!/bin/sh\nmain() { :; }\n")

    assert _walked(tmp_path) == set(source)


def test_a_tracked_out_or_coverage_folder_is_still_source(tmp_path):
    import subprocess

    tracked = ("src/out/writer.py", "src/coverage/policy.py")
    for name in (*tracked, "coverage/report.js"):
        _touch(tmp_path, name, "x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", *tracked], cwd=tmp_path, check=True)

    assert _walked(tmp_path) == set(tracked)


def test_single_file_reindex_skips_a_virtualenv_and_a_build_wrapper(tmp_path):
    from graph_os.ingest.base import is_excluded

    _touch(tmp_path, "env/pyvenv.cfg", "home = /usr/bin\n")
    _touch(tmp_path, "env/lib/mod.py", "x = 1\n")

    assert is_excluded("env/lib/mod.py", root=tmp_path)
    assert is_excluded("android/gradlew", root=tmp_path)
    assert not is_excluded("src/env/config.py", root=tmp_path)
