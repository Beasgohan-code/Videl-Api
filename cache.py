"""
Videl-Api Advanced Caching Layer

In-memory cache with TTL support, LRU eviction, and cache statistics.
Used for search results, metadata, lyrics, and source health checks.
"""

from __future__ import annotations

import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CacheEntry:
    value: Any
    expiry: float  # timestamp when entry expires
    hits: int = 0
    size: int = 0


class TTLCache:
    """Thread-safe TTL cache with LRU eviction."""

    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expired": 0,
            "sets": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None

            if time.time() > entry.expiry:
                del self._store[key]
                self._stats["expired"] += 1
                self._stats["misses"] += 1
                return None

            # Move to end (LRU)
            self._store.move_to_end(key)
            entry.hits += 1
            self._stats["hits"] += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            ttl = ttl or self._default_ttl
            expiry = time.time() + ttl
            size = self._estimate_size(value)

            if key in self._store:
                self._store.move_to_end(key)

            self._store[key] = CacheEntry(
                value=value, expiry=expiry, hits=0, size=size
            )
            self._stats["sets"] += 1

            # Evict if over max size
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
                self._stats["evictions"] += 1

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def has(self, key: str) -> bool:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            if time.time() > entry.expiry:
                del self._store[key]
                self._stats["expired"] += 1
                return False
            return True

    def stats(self) -> dict:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
            return {
                **self._stats,
                "size": len(self._store),
                "max_size": self._max_size,
                "hit_rate_percent": round(hit_rate, 2),
            }

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._store.items() if now > v.expiry
            ]
            for k in expired_keys:
                del self._store[k]
                self._stats["expired"] += 1
            return len(expired_keys)

    @staticmethod
    def _estimate_size(value: Any) -> int:
        try:
            import sys
            return sys.getsizeof(value)
        except Exception:
            return 1


# Global cache instances
search_cache = TTLCache(max_size=5000, default_ttl=180)   # 3 min for search
metadata_cache = TTLCache(max_size=5000, default_ttl=3600)  # 1 hour for metadata
lyrics_cache = TTLCache(max_size=5000, default_ttl=3600)   # 1 hour for lyrics
source_health_cache = TTLCache(max_size=1000, default_ttl=60)  # 1 min for health