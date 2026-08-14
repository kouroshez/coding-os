"""The hub refuses to open a port it cannot defend.

`SecurityGateMiddleware` checked the token per request and only when one was
set, so `COS_HUB_TOKEN` unset plus `COS_WEB_HOST=0.0.0.0` served every route —
including the full code graph — to anyone who could reach the port, with no
startup complaint. A warning is not a fix: by the time it scrolls past, the
port is open. These tests pin the refusal and, just as importantly, that
loopback behaviour is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from web.security import InsecureBindError, assert_bind_is_safe


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_HUB_TOKEN", raising=False)
    monkeypatch.delenv("COS_HUB_ALLOW_INSECURE_BIND", raising=False)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5", ""])
def test_loopback_binds_are_untouched(host: str) -> None:
    assert_bind_is_safe(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "10.0.0.4"])
def test_offloopback_without_token_is_refused(host: str) -> None:
    with pytest.raises(InsecureBindError) as exc:
        assert_bind_is_safe(host)
    message = str(exc.value)
    assert "COS_HUB_TOKEN" in message, "refusal must name the fix, not just the problem"


def test_unresolvable_hostname_is_treated_as_exposed() -> None:
    """Guessing 'probably local' is the assumption that leaves an API open."""
    with pytest.raises(InsecureBindError):
        assert_bind_is_safe("hub.internal.example")


def test_token_permits_the_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_HUB_TOKEN", "s3cret")
    assert_bind_is_safe("0.0.0.0")


def test_explicit_override_permits_the_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_HUB_ALLOW_INSECURE_BIND", "1")
    assert_bind_is_safe("0.0.0.0")


def test_create_app_enforces_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The factory is the uvicorn entry point, so the guard has to live there."""
    from web.server import create_app

    monkeypatch.setenv("COS_WEB_HOST", "0.0.0.0")
    with pytest.raises(InsecureBindError):
        create_app()


class TestDockerDefaults:
    """The shipped compose file is the quickstart most users actually run."""

    @staticmethod
    def _compose() -> dict:
        return yaml.safe_load((REPO / "docker-compose.yml").read_text())

    def test_port_is_published_to_host_loopback_by_default(self) -> None:
        ports = self._compose()["services"]["hub"]["ports"]
        assert any("127.0.0.1" in str(p) for p in ports), (
            f"compose publishes {ports} — a bare 9188:9188 exposes an "
            "unauthenticated hub on every host interface"
        )

    def test_bind_mounts_do_not_default_to_home(self) -> None:
        mounts = self._compose()["services"]["hub"]["volumes"]
        sources = [m.get("source", "") for m in mounts if isinstance(m, dict)]
        assert sources, "expected long-form bind mounts"
        home_defaults = [s for s in sources if "${HOME}" in s or ":-${HOME}" in s]
        assert not home_defaults, (
            f"compose mounts all of $HOME by default: {home_defaults} — every ssh key "
            "and password store, read-only but readable, to index one project"
        )
