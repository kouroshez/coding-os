from __future__ import annotations

from importlib import util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "src" / "adapters"


def _dispatch_adapter_ids() -> list[str]:
    ids = []
    for manifest_path in sorted(ADAPTERS.glob("*/adapter.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        entrypoints = manifest.get("runtime_entrypoints") or {}
        if "dispatch" in (entrypoints.get("capabilities") or []):
            ids.append(manifest_path.parent.name)
    return ids


def test_the_contract_covers_the_installed_dispatch_adapters() -> None:
    # Without this, a path or layout change that empties the glob makes every
    # parametrized case below vanish and the suite pass having tested nothing.
    covered = _dispatch_adapter_ids()

    assert {"claude", "codex"} <= set(covered), covered


def _dispatch_entrypoint(adapter_id: str) -> Path:
    manifest = yaml.safe_load((ADAPTERS / adapter_id / "adapter.yaml").read_text(encoding="utf-8"))
    filename = (manifest.get("runtime_entrypoints") or {}).get("dispatch") or "sdk_dispatcher.py"
    return ADAPTERS / adapter_id / str(filename)


def _load(adapter_id: str):
    path = _dispatch_entrypoint(adapter_id)
    spec = util.spec_from_file_location(f"test_{adapter_id}_capacity", path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Provider wordings differ, but an adapter that recognises none of these cannot
# open the capacity breaker at all — it retry-storms a limit that cannot succeed.
# Every adapter must classify at least one of them.
LIMIT_MESSAGES = (
    "429 rate limit exceeded",
    "Usage limit reached; try again in 47 seconds",
    "quota exceeded for this organization",
    "too many requests",
)


@pytest.mark.parametrize("adapter_id", _dispatch_adapter_ids())
def test_adapter_classifies_a_provider_limit_as_retryable_capacity(adapter_id: str) -> None:
    classify = _load(adapter_id)._failure_fields
    classified = [fields for fields in (classify("error", m) for m in LIMIT_MESSAGES)]

    capacity = [f for f in classified if f.get("error_category") == "capacity"]
    assert capacity, (
        f"{adapter_id} recognises none of the provider limit wordings; "
        "the capacity breaker can never open for it"
    )
    for fields in capacity:
        assert fields["retryable"] is True
        assert fields["outcome"] == "known_failed"


@pytest.mark.parametrize("adapter_id", _dispatch_adapter_ids())
def test_adapter_extracts_a_provider_supplied_retry_delay(adapter_id: str) -> None:
    fields = _load(adapter_id)._failure_fields(
        "error", "Usage limit reached; try again in 47 seconds"
    )

    assert fields["error_category"] == "capacity"
    assert fields["retry_after_s"] == 47


@pytest.mark.parametrize("adapter_id", _dispatch_adapter_ids())
def test_adapter_keeps_a_timeout_unknown_so_it_cannot_be_replayed(adapter_id: str) -> None:
    fields = _load(adapter_id)._failure_fields("timeout", "timed out")

    assert fields["error_category"] == "timeout"
    assert fields["outcome"] == "unknown"


@pytest.mark.parametrize("adapter_id", _dispatch_adapter_ids())
def test_adapter_does_not_treat_auth_failure_as_a_timed_limit(adapter_id: str) -> None:
    fields = _load(adapter_id)._failure_fields("error", "401 unauthorized")

    assert fields["error_category"] == "auth"
    assert fields.get("retryable") is not True


@pytest.mark.parametrize("adapter_id", _dispatch_adapter_ids())
def test_adapter_separates_provider_overload_from_your_own_quota(adapter_id: str) -> None:
    classify = _load(adapter_id)._failure_fields

    for message in ("529 overloaded_error: Overloaded", "500 api_error: internal error"):
        fields = classify("error", message)

        # Provider-side, not your quota: it must stay retryable and must NOT be
        # `capacity`, or a brief provider blip would cool your adapter for the
        # whole configured window.
        assert fields["error_category"] != "capacity", message
        assert fields["retryable"] is True, message
        assert fields["outcome"] == "unknown", message


@pytest.mark.parametrize("adapter_id", _dispatch_adapter_ids())
def test_adapter_never_reports_a_success_shape_for_a_failure(adapter_id: str) -> None:
    fields = _load(adapter_id)._failure_fields("error", "something nobody anticipated")

    assert fields["error_category"] is not None
    assert fields["outcome"] in ("known_failed", "unknown")
