"""
Videl-Api Advanced Task Scheduler

Cron-like task scheduler for recurring jobs: cleanup, cache maintenance,
source health probing, analytics aggregation, download retry.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


@dataclass
class ScheduledTask:
    name: str
    interval_seconds: float
    callback: Callable
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    enabled: bool = True

    def should_run(self, now: float) -> bool:
        if not self.enabled:
            return False
        if self.next_run is None:
            return True
        return now >= self.next_run

    def schedule_next(self, now: float) -> None:
        self.last_run = now
        self.next_run = now + self.interval_seconds
        self.run_count += 1

    def record_error(self, error: str) -> None:
        self.error_count += 1
        self.last_error = error


class TaskScheduler:
    """Async task scheduler with interval-based execution."""

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register(
        self,
        name: str,
        interval_seconds: float,
        callback: Callable,
        enabled: bool = True,
    ) -> None:
        self._tasks[name] = ScheduledTask(
            name=name,
            interval_seconds=interval_seconds,
            callback=callback,
            next_run=time.time() + interval_seconds,
            enabled=enabled,
        )

    def unregister(self, name: str) -> bool:
        if name in self._tasks:
            del self._tasks[name]
            return True
        return False

    def enable(self, name: str) -> bool:
        if name in self._tasks:
            self._tasks[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self._tasks:
            self._tasks[name].enabled = False
            return True
        return False

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        return self._tasks.get(name)

    def list_tasks(self) -> list[dict]:
        now = time.time()
        return [
            {
                "name": t.name,
                "interval_seconds": t.interval_seconds,
                "enabled": t.enabled,
                "run_count": t.run_count,
                "error_count": t.error_count,
                "last_run": (
                    datetime.fromtimestamp(t.last_run, tz=timezone.utc).isoformat()
                    if t.last_run else None
                ),
                "next_run": (
                    datetime.fromtimestamp(t.next_run, tz=timezone.utc).isoformat()
                    if t.next_run else None
                ),
                "last_error": t.last_error,
                "seconds_until_next": max(0, (t.next_run or 0) - now),
            }
            for t in self._tasks.values()
        ]

    async def _run_task(self, task: ScheduledTask, now: float) -> None:
        try:
            if asyncio.iscoroutinefunction(task.callback):
                await task.callback()
            else:
                task.callback()
            task.schedule_next(now)
        except Exception as exc:
            task.record_error(str(exc))
            # Still schedule next run so a failing task doesn't block forever
            task.schedule_next(now)

    async def _loop(self) -> None:
        while self._running:
            now = time.time()
            for task in list(self._tasks.values()):
                if task.should_run(now):
                    asyncio.create_task(self._run_task(task, now))
            await asyncio.sleep(1)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._loop())
        except RuntimeError:
            # No running loop yet; will be started when first awaited
            pass

    async def start_async(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


# Global scheduler instance
scheduler = TaskScheduler()


# ---------------------------------------------------------------------------
# Built-in maintenance tasks
# ---------------------------------------------------------------------------

async def _cache_cleanup_task():
    from cache import search_cache, metadata_cache, lyrics_cache, source_health_cache
    removed = 0
    for cache in (search_cache, metadata_cache, lyrics_cache, source_health_cache):
        removed += cache.cleanup_expired()
    if removed:
        print(f"[scheduler] cache cleanup: removed {removed} expired entries")


async def _source_health_task():
    """Placeholder: probes source health. Actual probing done per-request."""
    pass


def register_default_tasks() -> None:
    scheduler.register("cache_cleanup", 300, _cache_cleanup_task)  # every 5 min
    scheduler.register("source_health", 600, _source_health_task)  # every 10 min