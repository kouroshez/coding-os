"""Tests for the php scan_php_smells.py scanner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "src" / "core" / "skills" / "php" / "scripts")
)

import scan_php_smells as sp  # noqa: E402

CLEAN = '<?php\ndeclare(strict_types=1);\n$stmt = $pdo->prepare("SELECT 1");\n'


def test_clean_file_passes() -> None:
    assert sp.scan_text(CLEAN, filename="ok.php") == []


def test_eval_flagged() -> None:
    out = sp.scan_text("<?php declare(strict_types=1);\neval($x);", filename="x.php")
    assert any("eval()" in f for f in out)


def test_sql_injection_via_query_flagged() -> None:
    out = sp.scan_text(
        '<?php declare(strict_types=1);\n$db->query("SELECT $_GET[id]");', filename="x.php"
    )
    assert any("SQL injection" in f for f in out)


def test_shell_exec_with_request_flagged() -> None:
    out = sp.scan_text('<?php declare(strict_types=1);\nsystem($_GET["cmd"]);', filename="x.php")
    assert any("command injection" in f for f in out)


def test_weak_password_hash_flagged() -> None:
    out = sp.scan_text("<?php declare(strict_types=1);\n$h = md5($password);", filename="x.php")
    assert any("password_hash" in f for f in out)


def test_missing_strict_types_flagged() -> None:
    out = sp.scan_text("<?php\n$x = 1;", filename="x.php")
    assert any("strict_types" in f for f in out)


def test_comment_lines_ignored() -> None:
    out = sp.scan_text("<?php declare(strict_types=1);\n// eval($x) in a comment", filename="x.php")
    assert out == []
