"""The distribution must carry what the runtime resolves at import time.

Source-tree green is not distribution green: `cos hub start` serves the SPA from
`<web package>/ui/dist`, and that tree was excluded from package-data while the
release workflow built no UI — so a PyPI install answered "SPA not built yet" at
`/` and every source-tree test still passed. These tests inspect the artifact.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UI_DIST = REPO / "src" / "core" / "web" / "ui" / "dist"

# The SPA entry plus the hashed bundles it names — a wheel with index.html but no
# assets/ renders a blank page, which reads as "working" to a smoke test that
# only checks for a 200.
REQUIRED = ("web/ui/dist/index.html",)
FORBIDDEN_MARKERS = ("node_modules/", "web/ui/src/", "web/ui/tests/", "__pycache__/")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # In the release job the wheel that will actually be signed and uploaded
    # already exists — check THAT artifact rather than a rebuild of it, so the
    # gate cannot pass on a wheel other than the published one.
    prebuilt = os.environ.get("COS_WHEEL_PATH", "")
    if prebuilt:
        candidates = sorted(Path().glob(prebuilt)) if "*" in prebuilt else [Path(prebuilt)]
        assert candidates, f"COS_WHEEL_PATH matched nothing: {prebuilt}"
        assert len(candidates) == 1, f"COS_WHEEL_PATH is ambiguous: {candidates}"
        return candidates[0]

    if not UI_DIST.is_dir():
        pytest.skip("src/core/web/ui/dist absent — run `npm run build` in src/core/web/ui")
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")
    out = tmp_path_factory.mktemp("wheel")
    # setuptools stages into ./build and REUSES it: a wheel built after any
    # earlier build inherits that staging tree, so a packaging regression keeps
    # passing locally on files the current config no longer includes. Verified
    # by experiment — the same config produced 0 or 8 dist entries depending
    # only on whether ./build survived.
    shutil.rmtree(REPO / "build", ignore_errors=True)
    proc = subprocess.run(
        ["uv", "build", "--wheel", "--no-cache", "--out-dir", str(out), str(REPO)],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert proc.returncode == 0, f"wheel build failed:\n{proc.stdout}\n{proc.stderr}"
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, got {wheels}"
    return wheels[0]


@pytest.mark.slow
def test_wheel_ships_the_built_spa(wheel: Path) -> None:
    names = set(zipfile.ZipFile(wheel).namelist())
    missing = [n for n in REQUIRED if n not in names]
    assert not missing, f"wheel is missing the SPA entry point: {missing}"
    assets = [n for n in names if n.startswith("web/ui/dist/assets/")]
    assert assets, "wheel has index.html but no hashed assets — the page would render blank"


@pytest.mark.slow
def test_wheel_excludes_ui_sources_and_node_modules(wheel: Path) -> None:
    names = zipfile.ZipFile(wheel).namelist()
    leaked = [n for n in names if any(marker in n for marker in FORBIDDEN_MARKERS)]
    assert not leaked, f"build-time-only files leaked into the wheel: {leaked[:10]}"


@pytest.mark.slow
def test_wheel_index_references_a_bundled_asset(wheel: Path) -> None:
    """index.html names hashed bundles; each must exist in the same archive."""
    archive = zipfile.ZipFile(wheel)
    html = archive.read("web/ui/dist/index.html").decode()
    names = set(archive.namelist())
    quote = '"'
    referenced = {
        "web/ui/dist/" + part.split(quote, 1)[0]
        for part in html.split('="/')[1:]
        if part.split(quote, 1)[0].startswith("assets/")
    }
    assert referenced, f"index.html references no /assets/* bundle:\n{html[:400]}"
    missing = sorted(referenced - names)
    assert not missing, f"index.html references bundles absent from the wheel: {missing}"
