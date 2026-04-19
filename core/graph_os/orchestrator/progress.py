"""Progress reporting — thin wrapper over the metrics table (I.9).

PURPOSE:  Give orchestrator tasks a consistent way to emit metrics so
          `cos_graph_health` and `cos_metric_query` see the same
          counters. Keeps the handler code from importing SQLite
          directly.
INPUT:    sink (callable) — the backend that persists metrics. Tests
          pass a fake; production passes `cos_metric_record`.
OUTPUT:   per-role counters (files_processed, queue_depth, ...).
DEPENDS:  stdlib only.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("graph_os.orchestrator.progress")

MetricSink = Callable[[str, float, dict[str, Any]], None]


def _noop_sink(_name: str, _value: float, _tags: dict[str, Any]) -> None:
    return None


@dataclass
class ProgressReporter:
    """Thread-safe progress aggregator per role.

    PURPOSE:      Expose a small surface (record, snapshot) so roles
                  do not import metric-table internals. The sink is
                  pluggable.
    INPUT:        optional sink callable.
    OUTPUT:       `.snapshot()` returns {counter: int | float}.
    """

    sink: MetricSink = field(default_factory=lambda: _noop_sink)
    _counters: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, name: str, value: float = 1.0, **tags: Any) -> None:
        key = f"{name}|{tags}" if tags else name
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value
        try:
            self.sink(name, value, tags)
        except Exception as exc:  # noqa: BLE001
            logger.debug("progress sink failed: %s", exc)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._counters)


__all__ = ["ProgressReporter", "MetricSink"]
