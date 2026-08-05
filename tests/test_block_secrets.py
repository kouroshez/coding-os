"""Behavior tests for block-secrets.sh (audit N2 / 2b sk- regex, 2d skip-list)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "block-secrets.sh"

# Credential SHAPES, not credentials: composed at run time so the literal never
# exists in the tree for any scanner to match, per SECURITY.md § Test fixtures
# for secret detection.
_REAL_ANT = "sk-ant-api03-" + "A1b2C3d4" * 11  # 88-char alnum body
_REAL_PROJ = "sk-proj-" + "A1b2C3d4" * 6  # 48-char body
_REAL_CLASSIC = "sk-" + "T3BlbkFJ" * 6  # 48-char alnum


def _run(file_path: str, content: str) -> int:
    payload = {"tool_name": "Write", "tool_input": {"file_path": file_path, "content": content}}
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=10,
    )
    return proc.returncode


@pytest.mark.parametrize("secret", [_REAL_ANT, _REAL_PROJ, _REAL_CLASSIC])
def test_blocks_real_keys(secret: str) -> None:
    assert _run("src/app/config.py", f"KEY = '{secret}'") == 2, secret


def test_allows_kebab_slug() -> None:
    slug = "sk-product-identifier-some-long-internal-code-x-name"
    assert _run("src/app/config.py", f"const sku = '{slug}'") == 0


def test_scans_path_with_test_substring() -> None:
    # 'latest' contains 'test' but is not a test dir → must still be scanned.
    assert _run("src/latest/config.py", f"KEY='{_REAL_CLASSIC}'") == 2


def test_skips_real_test_fixture() -> None:
    assert _run("src/app/tests/fixtures/sample.py", f"KEY='{_REAL_CLASSIC}'") == 0
