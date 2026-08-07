from __future__ import annotations

from importlib import util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load(adapter_id: str):
    path = ROOT / "src" / "adapters" / adapter_id / "sdk_dispatcher.py"
    spec = util.spec_from_file_location(f"test_{adapter_id}_capacity", path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_normalizes_capacity_and_retry_delay() -> None:
    fields = _load("codex")._failure_fields("error", "Usage limit reached; try again in 47 seconds")

    assert fields == {
        "error_category": "capacity",
        "retryable": True,
        "retry_after_s": 47,
        "outcome": "known_failed",
    }


def test_claude_normalizes_capacity_without_provider_payload() -> None:
    fields = _load("claude")._failure_fields("error", "429 rate limit exceeded")

    assert fields["error_category"] == "capacity"
    assert fields["retryable"] is True
    assert fields["outcome"] == "known_failed"


def test_timeout_remains_unknown_and_cannot_fallback() -> None:
    for adapter_id in ("claude", "codex"):
        fields = _load(adapter_id)._failure_fields("timeout", "timed out")
        assert fields["error_category"] == "timeout"
        assert fields["outcome"] == "unknown"
