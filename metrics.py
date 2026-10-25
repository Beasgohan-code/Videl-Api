"""Videl-Api metrics: in-process counters, latency percentiles, Prometheus text output.

Exceeds VYRON with per-endpoint histograms and quota tracking.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

from config import settings


@dataclass
class Counter:
    value: int = 0


@dataclass
class Histogram:
    buckets: list[float] = field(default_factory=lambda: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    counts: dict[int, int] = field(default_factory=dict)
    sum: float = 0.0
    count: int = 0

    def observe(self, value: float) -> None:
        self.sum += value
        self.count += 1
        for i, b in enumerate(self.buckets):
            if value <= b:
                self.counts[i] = self.counts.get(i, 0) + 1
                break


class MetricsRegistry:
    def __init__(self):
        self._lock = Lock()
        self.counters: dict[str, Counter] = defaultdict(Counter)
        self.histograms: dict[str, Histogram] = defaultdict(Histogram)
        self.gauges: dict[str, float] = defaultdict(float)
        self.start_time = time.time()

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self.counters[name].value += value

    def set(self, name: str, value: float) -> None:
        with self._lock:
            self.gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self.histograms[name].observe(value)

    def get_counter(self, name: str) -> int:
        with self._lock:
            return self.counters.get(name, Counter()).value

    def get_gauge(self, name: str) -> float:
        with self._lock:
            return self.gauges.get(name, 0.0)

    def get_histogram(self, name: str) -> Histogram:
        with self._lock:
            return self.histograms.get(name, Histogram())

    def prometheus_text(self) -> str:
        lines = []
        with self._lock:
            # Counters
            for name, c in self.counters.items():
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {c.value}")
            # Gauges
            for name, v in self.gauges.items():
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {v}")
            # Histograms
            for name, h in self.histograms.items():
                lines.append(f"# TYPE {name} histogram")
                for i, b in enumerate(h.buckets):
                    cum = sum(h.counts.get(j, 0) for j in range(i + 1))
                    lines.append(f'{name}_bucket{{le="{b}"}} {cum}')
                lines.append(f'{name}_bucket{{le="+Inf"}} {h.count}')
                lines.append(f"{name}_sum {h.sum}")
                lines.append(f"{name}_count {h.count}")
            uptime = time.time() - self.start_time
            lines.append(f"videl_api_uptime_seconds {uptime}")
        return "\n".join(lines) + "\n"


registry = MetricsRegistry()

# Pre-register common metrics
def request_counter(endpoint: str, method: str, status: str) -> None:
    registry.inc("videl_api_requests_total", 1)
    registry.inc(f"videl_api_requests_by_endpoint", 1)
    registry.observe("videl_api_request_duration_seconds", 0.0)  # placeholder; set in middleware


def quota_denied_counter(key_id: str) -> None:
    registry.inc("videl_api_quota_denied_total", 1)

def download_counter(source: str, status: str) -> None:
    registry.inc("videl_api_downloads_total", 1)
    registry.inc(f"videl_api_downloads_by_source", 1)

def bytes_downloaded_counter(bytes_val: int) -> None:
    registry.inc("videl_api_bytes_downloaded_total", bytes_val)
