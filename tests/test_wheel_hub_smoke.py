"""A wheel installed into an empty venv must actually serve the Hub.

`tests/test_wheel_contents.py` proves the SPA files are *in* the archive; this
proves the installed package can *run*. The distinction is not academic — with
the SPA correctly packaged, `create_app()` still died twice on imports that only
resolve in the source tree (`logging_os` was not a distributed package, and a
route rebuilt a sys.path from source-tree depth). Every source-tree test passed
throughout.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UI_DIST = REPO / "src" / "core" / "web" / "ui" / "dist"
PLACEHOLDER = "SPA not built yet"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    # A refused connection is the normal state while the server boots, so it is
    # a status, not an exception — otherwise the readiness loop dies on its
    # first poll and every test errors before the hub has finished starting.
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


@pytest.fixture(scope="module")
def installed_hub(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, subprocess.Popen]:
    if not UI_DIST.is_dir():
        pytest.skip("src/core/web/ui/dist absent — run `npm run build` in src/core/web/ui")
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")

    work = tmp_path_factory.mktemp("hubsmoke")
    shutil.rmtree(REPO / "build", ignore_errors=True)
    build = subprocess.run(
        ["uv", "build", "--wheel", "--no-cache", "--out-dir", str(work), str(REPO)],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert build.returncode == 0, f"wheel build failed:\n{build.stderr}"
    wheel = next(iter(work.glob("*.whl")))

    venv = work / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=300)
    python = venv / "bin" / "python"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", str(wheel)],
        check=True,
        timeout=900,
    )

    port = _free_port()
    # uvicorn directly, not `cos hub start`: the CLI is a singleton that refuses
    # to start when any hub on the machine holds the pidfile, so the test would
    # silently probe the developer's running hub instead of this wheel.
    proc = subprocess.Popen(
        [
            str(python),
            "-c",
            "import uvicorn;from web.server import create_app;"
            f"uvicorn.run(create_app(), host='127.0.0.1', port={port}, log_level='warning')",
        ],
        cwd=work,
        env={
            "PATH": f"{venv / 'bin'}:/usr/bin:/bin",
            "HOME": str(work),
            "COS_STATE_DIR": str(work / "state"),
            "COS_WEB_PORT": str(port),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        if proc.poll() is not None:
            pytest.fail(f"hub exited early ({proc.returncode}):\n{proc.stdout.read()}")
        if _get(f"{base}/api/health")[0] == 200:
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("hub never became healthy")

    yield base, proc
    proc.terminate()
    proc.wait(timeout=30)


@pytest.mark.slow
def test_installed_hub_serves_the_spa(installed_hub: tuple[str, subprocess.Popen]) -> None:
    base, _ = installed_hub
    status, body = _get(f"{base}/")
    assert status == 200, f"GET / returned {status}"
    assert PLACEHOLDER not in body, "installed hub served the placeholder, not the SPA"
    assert "<div id=" in body or "<script" in body, f"unexpected body: {body[:200]}"


@pytest.mark.slow
def test_installed_hub_serves_the_hashed_bundles(
    installed_hub: tuple[str, subprocess.Popen],
) -> None:
    base, _ = installed_hub
    _, body = _get(f"{base}/")
    assets = [
        part.split('"', 1)[0]
        for part in body.split('="')[1:]
        if part.split('"', 1)[0].startswith("/assets/")
    ]
    assert assets, "index.html references no /assets/* bundle"
    status, _ = _get(f"{base}{assets[0]}")
    assert status == 200, f"{assets[0]} returned {status}"


@pytest.mark.slow
def test_installed_hub_api_responds(installed_hub: tuple[str, subprocess.Popen]) -> None:
    base, _ = installed_hub
    assert _get(f"{base}/api/health")[0] == 200
