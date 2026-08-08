"""Tests for I.11 ingestion — local, GitHub, ZIP + size guards."""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from graph_os.ingest import (
    GithubSize,
    IngestError,
    ZipSize,
    clone_github,
    extract_zip,
    walk_local,
)

# ---------------------------------------------------------------------------
# Local walk
# ---------------------------------------------------------------------------


class TestLocal:
    def test_walk_returns_plan(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.md").write_text("# hi")
        plan = walk_local(tmp_path)
        assert plan.alias == tmp_path.name
        assert len(plan.files) == 2

    def test_walk_collects_php(self, tmp_path):
        # .php must be in DEFAULT_INCLUDE so bulk reindex picks up
        # PHP/Laravel/WordPress/WHMCS files (the auto-reindex single-file path
        # already routed .php via _EXT_MAP; the walk did not collect them).
        (tmp_path / "plugin.php").write_text("<?php\nadd_action('init', 'x');")
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "ctrl.php").write_text("<?php\nclass C {}")
        plan = walk_local(tmp_path)
        php = [p for p in plan.files if str(p).endswith(".php")]
        assert len(php) == 2

    def test_exclude_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "b.py").write_text("")
        plan = walk_local(tmp_path)
        assert all(".git" not in str(p) for p in plan.files)

    def test_exclude_paths_drops_test_golden_fixtures(self, tmp_path):
        """tests/golden/ mirrors of real repo structure inflate the graph
        with duplicates that surface as 6 identical "adr" / "api-contracts"
        entries in the Hub UI sidebar. Path-segment exclude prunes them at
        walk time, separate from folder-name exclude (`golden` alone would
        over-match in consumer projects)."""
        # Real source — kept.
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "real.py").write_text("")
        # tests/golden — golden fixtures, dropped.
        golden = tmp_path / "tests" / "golden" / "claude_django"
        golden.mkdir(parents=True)
        (golden / "scaffold.py").write_text("")
        # Sibling tests/ content — kept (only the golden/ subtree is pruned).
        (tmp_path / "tests" / "real_test.py").write_text("")

        plan = walk_local(tmp_path)
        paths = [str(p.relative_to(tmp_path)) for p in plan.files]
        assert "src/real.py" in paths
        assert "tests/real_test.py" in paths
        assert not any("tests/golden" in p for p in paths), f"tests/golden survived prune: {paths}"

    def test_exclude_paths_does_not_match_partial_segment(self, tmp_path):
        """A folder named `golden_clone` next to `golden` must NOT be pruned —
        the segment match requires the literal sequence with a `/` boundary."""
        clone = tmp_path / "tests" / "golden_clone"
        clone.mkdir(parents=True)
        (clone / "f.py").write_text("")
        plan = walk_local(tmp_path)
        assert any("golden_clone" in str(p) for p in plan.files)

    def test_oversize_file_dropped_and_recorded(self, tmp_path):
        """A file over max_file_bytes is skipped but recorded in metadata so
        the drop is visible, not silent (TASK-293 logging-completeness)."""
        (tmp_path / "small.py").write_text("x = 1")
        (tmp_path / "huge.py").write_bytes(b"x = 1\n" * 1000)
        plan = walk_local(tmp_path, max_file_bytes=100)
        names = [p.name for p in plan.files]
        assert "small.py" in names
        assert "huge.py" not in names
        assert plan.metadata.get("skipped_oversize") == ["huge.py"]

    def test_symlink_skipped_and_counted(self, tmp_path):
        """Symlinks are skipped (target indexed on its own pass) but the count
        is surfaced in metadata so it isn't silent (TASK-302)."""
        (tmp_path / "real.py").write_text("x = 1")
        link = tmp_path / "alias.py"
        try:
            link.symlink_to(tmp_path / "real.py")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
        plan = walk_local(tmp_path)
        names = [p.name for p in plan.files]
        assert "real.py" in names
        assert "alias.py" not in names
        assert plan.metadata.get("skipped_symlink") == 1
        assert "skipped_read_error" in plan.metadata

    def test_unknown_path_raises(self, tmp_path):
        with pytest.raises(IngestError):
            walk_local(tmp_path / "missing")

    def test_size_cap_refuses(self, tmp_path):
        for i in range(3):
            (tmp_path / f"big_{i}.py").write_bytes(b"x" * 1000)
        with pytest.raises(IngestError):
            walk_local(tmp_path, max_size_bytes=500)

    def test_file_cap_refuses(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f_{i}.py").write_text("")
        with pytest.raises(IngestError):
            walk_local(tmp_path, max_files=3)


# ---------------------------------------------------------------------------
# .gitignore-aware walk (TASK-294)
# ---------------------------------------------------------------------------


class TestGitignore:
    def test_excludes_dir_not_in_denylist(self, tmp_path):
        """A custom output dir absent from DEFAULT_EXCLUDE but listed in
        .gitignore must be pruned, just as git would ignore it."""
        (tmp_path / ".gitignore").write_text("out/\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "real.py").write_text("")
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "generated.py").write_text("")
        plan = walk_local(tmp_path)
        paths = [p.relative_to(tmp_path).as_posix() for p in plan.files]
        assert "src/real.py" in paths
        assert not any(p.startswith("out/") for p in paths), paths

    def test_excludes_file_glob(self, tmp_path):
        """A file glob in .gitignore (e.g. *.gen.py) excludes matching files."""
        (tmp_path / ".gitignore").write_text("*.gen.py\n")
        (tmp_path / "keep.py").write_text("")
        (tmp_path / "schema.gen.py").write_text("")
        plan = walk_local(tmp_path)
        paths = [p.name for p in plan.files]
        assert "keep.py" in paths
        assert "schema.gen.py" not in paths

    def test_nested_gitignore_scoped_to_subtree(self, tmp_path):
        """A nested .gitignore applies only to its own subtree — a same-named
        file outside that subtree is still collected."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / ".gitignore").write_text("local.py\n")
        (pkg / "local.py").write_text("")
        (pkg / "keep.py").write_text("")
        (tmp_path / "local.py").write_text("")  # outside pkg/ — kept
        plan = walk_local(tmp_path)
        paths = [p.relative_to(tmp_path).as_posix() for p in plan.files]
        assert "local.py" in paths
        assert "pkg/keep.py" in paths
        assert "pkg/local.py" not in paths, paths

    def test_denylist_backstops_when_no_gitignore(self, tmp_path):
        """With no .gitignore at all, the static denylist still excludes
        node_modules — the .gitignore layer is additive, never required."""
        (tmp_path / "app.py").write_text("")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "dep.py").write_text("")
        plan = walk_local(tmp_path)
        assert all("node_modules" not in str(p) for p in plan.files)

    def test_falls_back_to_denylist_without_pathspec(self, tmp_path, monkeypatch):
        """pathspec unavailable → walk degrades cleanly: .gitignore is
        ignored but the denylist + normal collection still work (fail-open)."""
        from graph_os.ingest import base as ingest_base

        monkeypatch.setattr(ingest_base, "_pathspec", None)
        (tmp_path / ".gitignore").write_text("out/\n")
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "generated.py").write_text("")
        (tmp_path / "keep.py").write_text("")
        plan = walk_local(tmp_path)
        paths = [p.relative_to(tmp_path).as_posix() for p in plan.files]
        assert "keep.py" in paths
        # Without pathspec, out/ is NOT gitignore-pruned (denylist has no out/).
        assert "out/generated.py" in paths


# ---------------------------------------------------------------------------
# GitHub clone (mocked runner)
# ---------------------------------------------------------------------------


class TestGithub:
    def test_invalid_url(self):
        with pytest.raises(IngestError):
            clone_github("ftp://github.com/x/y")

    def test_non_github_url(self):
        with pytest.raises(IngestError):
            clone_github("https://gitlab.com/x/y")

    def test_clone_invokes_git_with_shallow(self, tmp_path, monkeypatch):
        calls = {}

        def fake_runner(cmd, **kwargs):
            calls["cmd"] = cmd
            # Create a fake target dir so walk_local succeeds.
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / "hello.py").write_text("x = 1")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        plan = clone_github(
            "https://github.com/acme/demo",
            alias="demo",
            clone_dir=tmp_path,
            runner=fake_runner,
        )
        assert "--depth" in calls["cmd"]
        assert "1" in calls["cmd"]
        assert plan.alias == "demo"
        assert any("hello.py" in str(p) for p in plan.files)

    def test_clone_timeout_raises(self, tmp_path):
        def slow_runner(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))

        with pytest.raises(IngestError, match="timed out"):
            clone_github(
                "https://github.com/a/b",
                clone_dir=tmp_path,
                size=GithubSize(timeout_seconds=1),
                runner=slow_runner,
            )

    def test_private_without_auth_rejected(self, tmp_path):
        def private_runner(cmd, **kwargs):
            raise subprocess.CalledProcessError(
                128, cmd, b"", b"fatal: could not read Username for 'https://github.com'\n"
            )

        with pytest.raises(IngestError, match="private"):
            clone_github(
                "https://github.com/private/repo",
                clone_dir=tmp_path,
                runner=private_runner,
            )

    def test_git_not_found(self, tmp_path):
        def missing_runner(cmd, **kwargs):
            raise FileNotFoundError("no git")

        with pytest.raises(IngestError, match="git executable"):
            clone_github(
                "https://github.com/a/b",
                clone_dir=tmp_path,
                runner=missing_runner,
            )


# ---------------------------------------------------------------------------
# ZIP ingestion
# ---------------------------------------------------------------------------


def _make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


class TestZip:
    def test_normal_archive(self, tmp_path):
        archive = _make_zip(
            tmp_path / "sample.zip",
            {"pkg/a.py": b"x = 1", "pkg/README.md": b"# x"},
        )
        plan = extract_zip(archive, out_dir=tmp_path / "out")
        assert plan.alias == "sample"
        assert len(plan.files) == 2

    def test_bad_zip_rejected(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip")
        with pytest.raises(IngestError):
            extract_zip(bad, out_dir=tmp_path / "out")

    def test_traversal_rejected(self, tmp_path):
        archive = _make_zip(
            tmp_path / "trav.zip",
            {"../evil.py": b"pwn"},
        )
        with pytest.raises(IngestError, match="traversal"):
            extract_zip(archive, out_dir=tmp_path / "out")

    def test_missing_archive(self, tmp_path):
        with pytest.raises(IngestError):
            extract_zip(tmp_path / "missing.zip", out_dir=tmp_path / "out")

    def test_size_cap(self, tmp_path):
        archive = _make_zip(
            tmp_path / "big.zip",
            {f"f{i}.py": b"x" * 1000 for i in range(5)},
        )
        with pytest.raises(IngestError, match="exceeds"):
            extract_zip(
                archive,
                out_dir=tmp_path / "out",
                size=ZipSize(max_size_bytes=1000),
            )
