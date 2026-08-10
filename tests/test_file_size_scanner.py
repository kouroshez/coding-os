"""The repo-wide half of the file-size budget: the scanner doctor + the Hub share.

`cos doctor`, `make check-file-size`, and `/api/health/file-size` all call
`scan()` rather than re-deriving thresholds, so these tests pin the one
definition every surface reads.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNER_PATH = REPO_ROOT / "src" / "core" / "scripts" / "check_file_size.py"


def _load():
    spec = importlib.util.spec_from_file_location("cos_check_file_size", SCANNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scanner = _load()


def _write(path: Path, lines: int, header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"value_{i} = {i}" for i in range(lines))
    path.write_text(f"{header}{body}\n" if header else f"{body}\n")


class TestTiers:
    def test_flags_a_file_over_the_ceiling_as_an_error(self, tmp_path: Path) -> None:
        _write(tmp_path / "big.py", 600)
        result = scanner.scan(repo_root=tmp_path)
        assert result["ok"] is False
        assert result["error_count"] == 1
        assert result["violations"][0]["tier"] == "error"

    def test_flags_the_warn_tier_without_failing(self, tmp_path: Path) -> None:
        _write(tmp_path / "growing.py", 450)
        result = scanner.scan(repo_root=tmp_path)
        assert result["ok"] is True
        assert result["warn_count"] == 1
        assert result["violations"][0]["tier"] == "warn"

    def test_stays_silent_below_the_warn_tier(self, tmp_path: Path) -> None:
        _write(tmp_path / "small.py", 120)
        assert scanner.scan(repo_root=tmp_path)["violations"] == []

    def test_thresholds_are_overridable(self, tmp_path: Path) -> None:
        _write(tmp_path / "small.py", 120)
        result = scanner.scan(repo_root=tmp_path, ceiling=100, warn_at=50)
        assert result["error_count"] == 1

    def test_worst_offender_is_listed_first(self, tmp_path: Path) -> None:
        _write(tmp_path / "medium.py", 550)
        _write(tmp_path / "worst.py", 900)
        violations = scanner.scan(repo_root=tmp_path)["violations"]
        assert violations[0]["file"].endswith("worst.py")


class TestExemptions:
    def test_skips_generated_files(self, tmp_path: Path) -> None:
        # The largest file in this repo is an openapi-typescript artifact; a
        # budget that counts it teaches the agent to ignore the whole check.
        _write(tmp_path / "api-types.ts", 900, header="/* This file was auto-generated. */\n")
        assert scanner.scan(repo_root=tmp_path)["violations"] == []

    def test_skips_vendored_and_generated_trees(self, tmp_path: Path) -> None:
        for segment in ("node_modules", "vendor", "migrations", "scaffold"):
            _write(tmp_path / segment / "big.py", 900)
        assert scanner.scan(repo_root=tmp_path)["violations"] == []

    def test_skips_non_source_suffixes(self, tmp_path: Path) -> None:
        _write(tmp_path / "data.json", 900)
        assert scanner.scan(repo_root=tmp_path)["violations"] == []


class TestCli:
    def test_json_mode_is_parseable_and_exits_nonzero_on_error(self, tmp_path: Path) -> None:
        _write(tmp_path / "big.py", 600)
        proc = subprocess.run(
            [sys.executable, str(SCANNER_PATH), "--json"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(proc.stdout)
        assert proc.returncode == 1
        assert payload["error_count"] == 1
        assert payload["ceiling"] == scanner.DEFAULT_CEILING

    def test_clean_tree_exits_zero(self, tmp_path: Path) -> None:
        _write(tmp_path / "small.py", 50)
        proc = subprocess.run(
            [sys.executable, str(SCANNER_PATH)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
        assert "OK:" in proc.stdout

    def test_help_style_invocation_does_not_hang(self, tmp_path: Path) -> None:
        # Regression: the shell predecessor deadlocked on a here-string once the
        # file listing passed the pipe buffer, so it never completed a real run.
        _write(tmp_path / "small.py", 50)
        proc = subprocess.run(
            [sys.executable, str(SCANNER_PATH), str(tmp_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
