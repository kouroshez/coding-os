from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core import logging_os
from core.logging_os import bridge


@pytest.fixture
def temp_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("COS_LOG_FILE", raising=False)
    monkeypatch.delenv("COS_LOG_LEVEL", raising=False)
    yield tmp_path
    bridge.uninstall_bridge()


def test_setup_installs_stdlib_bridge_handler(temp_state: Path) -> None:
    logging_os.setup(level="info")
    root_handlers = logging.getLogger().handlers
    bridge_handlers = [h for h in root_handlers if isinstance(h, bridge.LoggingOsHandler)]
    assert len(bridge_handlers) == 1


def test_stdlib_logger_warning_routes_through_cos_log(temp_state: Path) -> None:
    logging_os.setup(level="info")
    logger = logging.getLogger("core.thinking_os.server")
    logger.warning("disk almost full")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip().splitlines()[-1])
    assert parsed["lvl"] == "WARN"
    assert parsed["scope"] == "core.thinking_os.server"
    assert parsed["msg"] == "disk almost full"


def test_stdlib_logger_below_level_dropped(temp_state: Path) -> None:
    logging_os.setup(level="warn")
    logger = logging.getLogger("core.thinking_os.task")
    logger.info("muted info")
    logger.warning("kept warn")
    text_log = (temp_state / ".cos.log").read_text()
    assert "muted info" not in text_log
    assert "kept warn" in text_log


def test_stdlib_main_logger_normalised_to_dotted_scope(temp_state: Path) -> None:
    logging_os.setup(level="debug")
    logger = logging.getLogger("__main__")
    logger.info("from main")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip().splitlines()[-1])
    assert parsed["scope"] == "py.main"


def test_setup_idempotent_no_handler_duplication(temp_state: Path) -> None:
    logging_os.setup(level="info")
    logging_os.setup(level="info")
    logging_os.setup(level="info")
    bridge_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, bridge.LoggingOsHandler)
    ]
    assert len(bridge_handlers) == 1


def test_uninstall_removes_bridge(temp_state: Path) -> None:
    logging_os.setup(level="info")
    logging_os.uninstall_bridge()
    bridge_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, bridge.LoggingOsHandler)
    ]
    assert bridge_handlers == []


def test_setup_can_skip_bridge_install(temp_state: Path) -> None:
    logging_os.setup(level="info", install_stdlib_bridge=False)
    bridge_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, bridge.LoggingOsHandler)
    ]
    assert bridge_handlers == []


def test_logger_with_dashes_normalised(temp_state: Path) -> None:
    logging_os.setup(level="info")
    logger = logging.getLogger("hook.enforce-skill")
    logger.warning("graph-explorer not loaded")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip().splitlines()[-1])
    assert parsed["scope"] == "hook.enforce_skill"
