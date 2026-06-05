"""Tests for the deployment-cicd lint_workflow.py linter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "deployment-cicd" / "scripts"))

import lint_workflow as lw  # noqa: E402

GOOD = """name: ci
on: [push]
jobs:
  test:
    timeout-minutes: 10
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test
"""


def test_good_workflow_clean() -> None:
    assert lw.scan_text(GOOD, filename="ci.yml") == []


def test_moving_ref_flagged() -> None:
    out = lw.scan_text("jobs:\n  t:\n    timeout-minutes: 5\n    steps:\n      - uses: actions/checkout@main\n",
                       filename="x.yml")
    assert any("moving ref" in f for f in out)


def test_echoed_secret_flagged() -> None:
    out = lw.scan_text("jobs:\n  t:\n    timeout-minutes: 5\n    steps:\n      - run: echo ${{ secrets.TOKEN }}\n",
                       filename="x.yml")
    assert any("secret echoed" in f for f in out)


def test_missing_timeout_flagged() -> None:
    out = lw.scan_text("jobs:\n  t:\n    steps:\n      - uses: actions/checkout@v4\n", filename="x.yml")
    assert any("timeout-minutes" in f for f in out)


def test_curl_bash_flagged() -> None:
    out = lw.scan_text("jobs:\n  t:\n    timeout-minutes: 5\n    steps:\n      - run: curl https://x | bash\n",
                       filename="x.yml")
    assert any("curl | bash" in f for f in out)
