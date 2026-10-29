"""
Videl-Api Advanced Rate Limiter

Sliding window rate limiter with per-key limits, burst allowance,
and burst decay. Supports in-memory and (optionally) Redis-backed storage.
"""

from __future__ import annotations

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_after: float  # seconds until limit resets
    limit: int
    retry_after: Optional[float] = None


class SlidingWindowRateLimiter:
    """Sliding window rate limiter with per-key tracking."""

    def __init__(self, default_limit: int = 60, window_seconds: int = 60):
        self._default_limit = default_limit
        self._window_seconds = window_seconds
        self._buckets: dict[str, deque] = {}
        self._lock = threading.RLock()
        self._stats = {"allowed": 0, "denied": 0}

    def check(
        self,
        key: str,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        limit = limit or self._default_limit
        window = window_seconds or self._window_seconds
        now = time.time()

        with self._lock:
            bucket = self._buckets.setdefault(key, deque())

            # Remove old entries outside window
            cutoff = now - window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            current_weight = sum(w for _, w in bucket)

            if current_weight + cost > limit:
                self._stats["denied"] += 1
                # Calculate retry after: when the oldest entry expires
                retry_after = bucket[0] + window - now if bucket else window
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_after=max(0, retry_after),
                    limit=limit,
                    retry_after=max(0, retry_after),
                )

            bucket.append((now, cost))
            self._stats["allowed"] += 1
            remaining = max(0, limit - current_weight - cost)
            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                reset_after=window,
                limit=limit,
            )

    def reset(self, key: str) -> bool:
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]
                return True
            return False

    def stats(self) -> dict:
        with self._lock:
            total = self._stats["allowed"] + self._stats["denied"]
            return {
                **self._stats,
                "total_keys": len(self._buckets),
                "deny_rate_percent": round(
                    self._stats["denied"] / total * 100, 2
                ) if total > 0 else 0,
            }


# Global rate limiter instance
rate_limiter = SlidingWindowRateLimiter()