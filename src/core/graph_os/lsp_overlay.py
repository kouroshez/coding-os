"""graph_os — LSP overlay (I.5).

DEPENDS:  stdlib subprocess / threading; the real LSP binaries are
          discovered at runtime from $PATH. The binary contract is
          hidden behind `LspDriver` so unit tests can swap in a fake.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess  # noqa: F401 — kept for FakeLspDriver signature parity
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger("graph_os.lsp_overlay")

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_FAILURE_WINDOW_SECONDS = 60.0
DEFAULT_MAX_FAILURES = 3
DEFAULT_DEGRADE_COOLDOWN_SECONDS = 300.0  # 5 min cooldown after tripping
DEFAULT_WARM_START_TIMEOUT_SECONDS = 120.0


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LspOverlayResult:
    """One LSP-raised resolution of a symbol reference."""

    status: str
    uid: str | None = None
    kind: str | None = None
    confidence: float = 0.0
    note: str | None = None


@dataclass
class _BreakerState:
    """Circuit-breaker counters (thread-owned; protected by a Lock)."""

    failure_timestamps: list[float] = field(default_factory=list)
    tripped_until: float = 0.0


# ---------------------------------------------------------------------------
# Protocol — the LSP driver is pluggable for testing.
# ---------------------------------------------------------------------------


class LspDriver(Protocol):
    """Minimum surface graph_os needs from any language-server client."""

    language: str

    def warm_start(self, *, timeout: float = DEFAULT_WARM_START_TIMEOUT_SECONDS) -> bool:
        """Return True once the server is ready to answer resolves."""

    def resolve(
        self,
        *,
        file_path: str,
        symbol: str,
        timeout: float,
    ) -> LspOverlayResult:
        """Resolve `symbol` inside `file_path`."""

    def shutdown(self) -> None:
        """Terminate the backing subprocess (idempotent)."""


# ---------------------------------------------------------------------------
# Subprocess-backed driver (pyright). Kept minimal — the wire protocol
# lives in `_PyrightLspDriver.resolve` so the overlay itself stays pure.
# ---------------------------------------------------------------------------


class _PyrightLspDriver:
    """Real pyright driver — wires `pyright-langserver` over LSP stdio.

    DEPENDS:      pyright + pyright-langserver on PATH; lsp_client.py.
    """

    language = "python"

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        binary: str | None = None,
        log_path: str | None = None,
    ) -> None:
        self.binary = binary or shutil.which("pyright-langserver") or "pyright-langserver"
        self.log_path = log_path or ".coding-os/.graph-lsp.log"
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self._client: Any = None
        self._opened_files: set[str] = set()

    def warm_start(self, *, timeout: float = DEFAULT_WARM_START_TIMEOUT_SECONDS) -> bool:
        if self._client is not None:
            return True
        if not shutil.which(self.binary):
            logger.debug("pyright-langserver not on PATH; LSP overlay stays disabled")
            return False
        try:
            from .lsp_client import (
                LspClient,
                LspClientError,
            )
        except ImportError as exc:
            logger.debug("lsp_client import failed: %s", exc)
            return False
        try:
            client = LspClient(
                command=[self.binary, "--stdio"],
                project_root=self.project_root,
                startup_timeout=timeout,
                request_timeout=5.0,
            )
            client.start()
            if not client.initialize():
                client.shutdown()
                return False
        except LspClientError as exc:
            logger.debug("pyright warm-start failed: %s", exc)
            return False
        self._client = client
        return True

    def resolve(
        self,
        *,
        file_path: str,
        symbol: str,
        timeout: float,
    ) -> LspOverlayResult:
        # The overlay's LspOverlay wraps per-call timeouts; the driver
        # passes the timeout down to goto_definition via the client
        # request_timeout set at warm-start time.
        _ = timeout
        from .lsp_client import LspClientError

        if self._client is None:
            return LspOverlayResult(status="unavailable", note="warm_start not called")
        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            abs_path = (self.project_root / file_path).resolve()
        if not abs_path.exists():
            return LspOverlayResult(status="unavailable", note="file missing")
        if str(abs_path) not in self._opened_files:
            self._client.did_open(abs_path, language_id="python")
            self._opened_files.add(str(abs_path))
        line_idx, char_idx = _locate_symbol(abs_path, symbol)
        if line_idx < 0:
            return LspOverlayResult(status="unavailable", note="symbol not found")
        try:
            locations = self._client.goto_definition(abs_path, line_idx, char_idx)
        except LspClientError as exc:
            raise RuntimeError(str(exc)) from exc
        if not locations:
            return LspOverlayResult(status="ok", note="no definition")
        first = locations[0]
        target = first.get("targetUri") or first.get("uri") or ""
        range_info = first.get("targetRange") or first.get("range") or {}
        start = range_info.get("start", {})
        uid = (
            f"code:lsp:{target}:{start.get('line', 0)}:{start.get('character', 0)}"
            if target
            else None
        )
        return LspOverlayResult(
            status="ok",
            uid=uid,
            kind="code:definition",
            confidence=0.95,
            note=target or None,
        )

    def shutdown(self) -> None:
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception as exc:
                logger.debug("pyright shutdown suppressed: %s", exc)
            finally:
                self._client = None
                self._opened_files.clear()


def _locate_symbol(path: Path, symbol: str) -> tuple[int, int]:
    """Return (line, character) of the first `symbol` occurrence in `path`.

    A deliberately dumb scan: LSP hover/definition demands a position,
    and the overlay caller (extractor) already has a nearby candidate
    in mind. `-1, -1` on miss so the caller knows to skip.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh):
                idx = line.find(symbol)
                if idx >= 0:
                    return (lineno, idx)
    except OSError:
        return (-1, -1)
    return (-1, -1)


# ---------------------------------------------------------------------------
# Fake driver — used by tests and as a drop-in when LSP is disabled.
# ---------------------------------------------------------------------------


class FakeLspDriver:
    """Deterministic fake driver for tests."""

    language = "python"

    def __init__(
        self,
        *,
        resolver: Callable[[str, str], LspOverlayResult] | None = None,
        latency: float = 0.0,
        warm_start_latency: float = 0.0,
        warm_start_succeeds: bool = True,
    ) -> None:
        self.resolver = resolver or (lambda _f, _s: LspOverlayResult(status="ok"))
        self.latency = latency
        self.warm_start_latency = warm_start_latency
        self.warm_start_succeeds = warm_start_succeeds
        self.warm_start_called = 0
        self.resolve_calls = 0
        self.shutdown_called = 0

    def warm_start(self, *, timeout: float = DEFAULT_WARM_START_TIMEOUT_SECONDS) -> bool:
        self.warm_start_called += 1
        if self.warm_start_latency > timeout:
            return False
        if self.warm_start_latency > 0:
            time.sleep(self.warm_start_latency)
        return self.warm_start_succeeds

    def resolve(self, *, file_path: str, symbol: str, timeout: float) -> LspOverlayResult:
        self.resolve_calls += 1
        if self.latency > timeout:
            raise _ResolveTimeout(self.latency)
        if self.latency > 0:
            time.sleep(self.latency)
        return self.resolver(file_path, symbol)

    def shutdown(self) -> None:
        self.shutdown_called += 1


class _ResolveTimeout(RuntimeError):
    def __init__(self, latency: float) -> None:
        super().__init__(f"resolve exceeded timeout (latency={latency:.2f}s)")


# ---------------------------------------------------------------------------
# The overlay itself
# ---------------------------------------------------------------------------


class LspOverlay:
    """Thread-safe overlay wrapping a single LSP driver.

    DEPENDS:  LspDriver implementation.
    """

    def __init__(
        self,
        driver: LspDriver,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        failure_window_seconds: float = DEFAULT_FAILURE_WINDOW_SECONDS,
        max_failures: int = DEFAULT_MAX_FAILURES,
        degrade_cooldown_seconds: float = DEFAULT_DEGRADE_COOLDOWN_SECONDS,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._driver = driver
        self._timeout = timeout_seconds
        self._window = failure_window_seconds
        self._max_failures = max_failures
        self._cooldown = degrade_cooldown_seconds
        self._enabled = enabled
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], LspOverlayResult] = {}
        self._breaker = _BreakerState()
        self._warm: bool = False

    # -- Lifecycle ---------------------------------------------------------

    @property
    def language(self) -> str:
        return getattr(self._driver, "language", "unknown")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def state(self) -> str:
        """High-level state — feeds into cos_graph_health()."""
        if not self._enabled:
            return "disabled"
        if self._breaker.tripped_until > self._clock():
            return "degraded"
        if not self._warm:
            return "cold"
        return "ready"

    def warm_start(self) -> bool:
        if not self._enabled:
            return False
        ok = bool(self._driver.warm_start())
        self._warm = ok
        return ok

    def shutdown(self) -> None:
        self._driver.shutdown()
        self._warm = False
        with self._lock:
            self._cache.clear()

    # -- Lookup ------------------------------------------------------------

    def lookup(self, *, file_path: str, symbol: str) -> LspOverlayResult:
        """Resolve a symbol via the overlay — cached, timeout-bounded,
        and circuit-breaker-aware."""
        if not self._enabled:
            return LspOverlayResult(status="unavailable", note="disabled")
        now = self._clock()
        if self._breaker.tripped_until > now:
            return LspOverlayResult(status="unavailable", note="circuit_open")

        key = (file_path, symbol)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit

        try:
            result = self._driver.resolve(file_path=file_path, symbol=symbol, timeout=self._timeout)
        except _ResolveTimeout as exc:
            self._record_failure()
            return LspOverlayResult(status="timeout", note=str(exc))
        except Exception as exc:
            self._record_failure()
            logger.debug("LSP resolve(%s::%s) failed: %s", file_path, symbol, exc)
            return LspOverlayResult(status="unavailable", note=str(exc))

        if result.status == "ok":
            with self._lock:
                self._cache[key] = result
        elif result.status in {"timeout", "error"}:
            self._record_failure()
        return result

    # -- Internal ----------------------------------------------------------

    def _record_failure(self) -> None:
        """Book-keep the failure and possibly trip the breaker."""
        now = self._clock()
        with self._lock:
            self._breaker.failure_timestamps.append(now)
            cutoff = now - self._window
            self._breaker.failure_timestamps = [
                t for t in self._breaker.failure_timestamps if t >= cutoff
            ]
            if len(self._breaker.failure_timestamps) >= self._max_failures:
                self._breaker.tripped_until = now + self._cooldown
                # Clear counters so after cooldown we start fresh.
                self._breaker.failure_timestamps = []
                logger.info(
                    "LSP overlay (%s) degraded for %.0fs",
                    self.language,
                    self._cooldown,
                )

    # -- Debug helpers (used by cos_graph_health + tests) ------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a dict describing the overlay's live state."""
        with self._lock:
            return {
                "language": self.language,
                "enabled": self._enabled,
                "state": self.state,
                "warm": self._warm,
                "cache_size": len(self._cache),
                "tripped_until": self._breaker.tripped_until,
                "recent_failures": len(self._breaker.failure_timestamps),
            }


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def build_overlay(
    language: str = "python",
    *,
    config: dict[str, Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> LspOverlay:
    """Construct an overlay from config — env / rag-config.yaml."""
    cfg = dict(config or {})
    enabled = cfg.pop("enabled", None)
    if enabled is None:
        enabled = os.environ.get("COS_LSP_ENABLED", "1") not in {"0", "false", "False"}

    if cfg.pop("fake", False):
        driver: LspDriver = FakeLspDriver(**cfg)
    else:
        if language == "python":
            driver = _PyrightLspDriver()
        else:
            logger.info("LSP overlay: language %s not supported yet", language)
            enabled = False
            driver = FakeLspDriver(warm_start_succeeds=False)

    return LspOverlay(driver, enabled=bool(enabled), clock=clock)


__all__ = [
    "DEFAULT_DEGRADE_COOLDOWN_SECONDS",
    "DEFAULT_FAILURE_WINDOW_SECONDS",
    "DEFAULT_MAX_FAILURES",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_WARM_START_TIMEOUT_SECONDS",
    "FakeLspDriver",
    "LspDriver",
    "LspOverlay",
    "LspOverlayResult",
    "build_overlay",
]
