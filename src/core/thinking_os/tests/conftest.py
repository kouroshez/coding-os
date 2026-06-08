"""thinking_os test fixtures.

Puts core/thinking_os on sys.path so tests using bare imports
(``from cognition import ...``, ``from database import ...``) resolve the
same way the MCP server does at runtime. Without this conftest,
``pytest core/thinking_os/tests/`` collects but cannot import these
modules and aborts with ModuleNotFoundError. Mirrors the pattern in
core/graph_os/tests/conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THINKING_OS_DIR = Path(__file__).resolve().parent.parent

if str(_THINKING_OS_DIR) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR))
if str(_THINKING_OS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR.parent))


@pytest.fixture(autouse=True)
def _isolate_durable_log_db(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect the durable log DB so test-deliberate errors never persist.

    Importing thinking_os.server installs the logging_os stdlib bridge
    process-globally, so every logger.error/.warning from production code under
    test routes to the durable log_events store at COS_DB_PATH. The error-path
    fixtures here (test_envelope.py's cos_fake_unshrinkable, embed_text with a
    bogus model) log on purpose; without this redirect those land in the real
    .coding-os/coding-os.db and the nightly error-sweep files them as phantom
    bug tasks (TASK-243/244). Tests that need a real DB set their own
    COS_DB_PATH after this autouse fixture, so last-write-wins keeps them green.
    """
    tmp_root = tmp_path_factory.mktemp("log_isolate", numbered=True)
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_root / ".coding-os"))
    monkeypatch.setenv("COS_DB_PATH", str(tmp_root / ".coding-os" / "coding-os.db"))
