"""graph-os — LSP overlay (I.5).

PURPOSE:  Share one long-lived pyright / tsserver per graph-os process
          across every indexer worker and overlay its higher-precision
          symbol resolutions onto tree-sitter / AST edges. Includes a
          circuit breaker so a misbehaving LSP does not take down the
          pipeline.
INPUT:    `LspOverlay.lookup(file, symbol)` from the call-site resolver.
OUTPUT:   `LspOverlayResult` carrying resolved uids + evidence.
DEPENDS:  stdlib subprocess / threading; the real LSP binaries are
          discovered at runtime from $PATH. The binary contract is
          hidden behind `LspDriver` so unit tests can swap in a fake.
NOTES:    This module never crashes the caller. All failures are
          logged and translated into `unavailable` results — the
          extractor keeps its tree-sitter confidence rather than
          raising. See plan §7.4 for the latency budget.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

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
    """One LSP-raised resolution of a symbol reference.

    PURPOSE:  Structured signal returned to the extractor so edges can
              be upserted with a richer evidence trail.
    INPUT:    uid of the resolved target + LSP kind + raw server hint.
    OUTPUT:   used as extra evidence rows by code_python / code_ts.
    NOTES:    `status` is "ok", "unavailable", or "timeout"; callers
              use this to decide whether to keep the tree-sitter
              confidence or overwrite it.
    """

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
    """Minimum surface graph-os needs from any language-server client.

    PURPOSE:  Hide pyright / tsserver behind a testable boundary.
    INPUT:    see per-method signatures.
    OUTPUT:   see per-method signatures.
    NOTES:    Real drivers wrap subprocess pipes; unit tests supply a
              deterministic fake via `FakeLspDriver`.
    """

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
    """Real pyright driver.

    Not exercised in unit tests — the overlay is tested through
    FakeLspDriver. Production wiring happens inside the orchestrator's
    `lsp:warm-start` role, which constructs this class once and hands
    it to `LspOverlay.attach`.
    """

    language = "python"

    def __init__(
        self,
        *,
        binary: str | None = None,
        log_path: str | None = None,
    ) -> None:
        self.binary = binary or shutil.which("pyright") or "pyright"
        self.log_path = log_path or ".coding-os/.graph-lsp.log"
        self._process: subprocess.Popen[bytes] | None = None
        self._started = False

    def warm_start(self, *, timeout: float = DEFAULT_WARM_START_TIMEOUT_SECONDS) -> bool:
        if self._started:
            return True
        if not shutil.which(self.binary):
            return False
        try:
            self._process = subprocess.Popen(  # noqa: S603
                [self.binary, "--outputjson"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("pyright failed to spawn: %s", exc)
            return False
        # Real warm-up would exchange `initialize` / `initialized` LSP
        # messages here. Kept as a stub because pyright is lazy-loaded
        # by individual resolves in this baseline.
        self._started = True
        return True

    def resolve(
        self,
        *,
        file_path: str,
        symbol: str,
        timeout: float,
    ) -> LspOverlayResult:
        if not self._started:
            return LspOverlayResult(status="unavailable", note="warm_start not called")
        # A full LSP client is out of scope for I.5; the overlay is wired
        # to accept the result shape, but the subprocess-level protocol
        # is deferred to I.5b (adapter hardening pass).
        return LspOverlayResult(
            status="unavailable", note="pyright-subprocess-not-implemented"
        )

    def shutdown(self) -> None:
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug("pyright shutdown: %s", exc)
            finally:
                self._process = None
                self._started = False


# ---------------------------------------------------------------------------
# Fake driver — used by tests and as a drop-in when LSP is disabled.
# ---------------------------------------------------------------------------


class FakeLspDriver:
    """Deterministic fake driver for tests.

    PURPOSE:  Exercise the overlay's circuit-breaker / cache / timeout
              logic without pyright.
    INPUT:    a `resolver` callable that maps (file, symbol) to an
              LspOverlayResult OR raises. `latency` simulates server
              RTT so timeout tests are meaningful.
    """

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

    def resolve(
        self, *, file_path: str, symbol: str, timeout: float
    ) -> LspOverlayResult:
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

    PURPOSE:  Funnel every indexer worker's symbol lookup through one
              driver, cache positive resolves for reuse, and trip a
              circuit breaker when the server starts crashing so the
              pipeline stays healthy.
    INPUT:    see __init__.
    OUTPUT:   LspOverlayResult per `lookup(...)`.
    DEPENDS:  LspDriver implementation.
    NOTES:    A tripped breaker is released after the cooldown; `state`
              exposes the live transition for `cos_graph_health`.
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
            result = self._driver.resolve(
                file_path=file_path, symbol=symbol, timeout=self._timeout
            )
        except _ResolveTimeout as exc:
            self._record_failure()
            return LspOverlayResult(status="timeout", note=str(exc))
        except Exception as exc:  # noqa: BLE001
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
    """Construct an overlay from config — env / rag-config.yaml.

    PURPOSE:      Single entry for the orchestrator's `lsp:warm-start`
                  role. Honours `COS_LSP_ENABLED=0` to opt out; uses a
                  FakeLspDriver when `config.fake=True`.
    INPUT:        language id + optional config dict.
    OUTPUT:       LspOverlay (possibly disabled).
    NOTES:        Returning a disabled overlay rather than None keeps
                  call-site code branch-free (always lookup, check
                  state, proceed).
    """
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
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_FAILURE_WINDOW_SECONDS",
    "DEFAULT_MAX_FAILURES",
    "DEFAULT_DEGRADE_COOLDOWN_SECONDS",
    "DEFAULT_WARM_START_TIMEOUT_SECONDS",
    "FakeLspDriver",
    "LspDriver",
    "LspOverlay",
    "LspOverlayResult",
    "build_overlay",
]
