"""Tests for the end-to-end-testing lint_e2e.py Playwright spec linter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "core"
        / "skills"
        / "end-to-end-testing"
        / "scripts"
    ),
)

import lint_e2e as le  # noqa: E402

GOOD = """
test('login', async ({ page }) => {
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByText('Welcome')).toBeVisible();
});
"""


def test_good_spec_clean() -> None:
    assert le.scan_text(GOOD, filename="ok.spec.ts") == []


def test_hard_sleep_flagged() -> None:
    out = le.scan_text(
        "test('x', async () => { await page.waitForTimeout(2000); await expect(x).toBeVisible(); });",
        filename="x.spec.ts",
    )
    assert any("hard sleep" in f for f in out)


def test_nth_child_selector_flagged() -> None:
    out = le.scan_text(
        "test('x', async () => { page.locator('ul li:nth-child(2)'); expect(1); });",
        filename="x.spec.ts",
    )
    assert any("nth-child" in f for f in out)


def test_test_without_assertion_flagged() -> None:
    out = le.scan_text(
        "test('noop', async ({ page }) => { await page.goto('/'); });", filename="x.spec.ts"
    )
    assert any("asserts nothing" in f for f in out)


def test_comment_ignored() -> None:
    out = le.scan_text(
        "// await page.waitForTimeout(1000)\ntest('x', async()=>{ expect(1); });",
        filename="x.spec.ts",
    )
    assert out == []
