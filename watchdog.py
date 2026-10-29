"""
Videl-Api Keep-Alive Watchdog

Monitors application health and keeps critical components alive:
- Periodic health checks of all subsystems
- Automatic recovery of failed components
- Metrics collection and reporting
- WebSocket connection health monitoring
- Download queue health monitoring
- Cache health monitoring
- Alerts on unhealthy states
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from cache import search_cache, metadata_cache, lyrics_cache, source_health_cache
from config import settings
from download_manager import download_manager
from logger import get_logger, log_error
from plugins import plugin_manager
from rate_limit import rate_limiter
from scheduler import scheduler
from websocket_manager import ws_manager

logger = get_logger("videl.watchdog")


@dataclass
class ComponentHealth:
    name: str
    healthy: bool
    last_check: float
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


class Watchdog:
    """Keep-alive watchdog that monitors and recovers application components."""

    def __init__(
        self,
        check_interval: float = 30.0,
        recovery_interval: float = 60.0,
        unhealthy_threshold: int = 3,
    ):
        self.check_interval = check_interval
        self.recovery_interval = recovery_interval
        self.unhealthy_threshold = unhealthy_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None
        self._health: dict[str, ComponentHealth] = {}
        self._failure_counts: dict[str, int] = {}
        self._recovery_handlers: dict[str, Callable[[], Any]] = {}
        self.start_time = time.time()

    def register_recovery(self, component: str, handler: Callable[[], Any]) -> None:
        """Register a recovery handler for a component."""
        self._recovery_handlers[component] = handler

    def _record_health(self, name: str, healthy: bool, error: Optional[str] = None, details: Optional[dict] = None) -> None:
        now = time.time()
        self._health[name] = ComponentHealth(
            name=name,
            healthy=healthy,
            last_check=now,
            error=error,
            details=details or {},
        )
        if healthy:
            self._failure_counts[name] = 0
        else:
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1

    def get_health(self) -> dict[str, Any]:
        """Return the current health status of all components."""
        overall_healthy = all(h.healthy for h in self._health.values())
        return {
            "status": "healthy" if overall_healthy else "degraded",
            "uptime_seconds": round(time.time() - self.start_time, 2),
            "check_interval": self.check_interval,
            "components": {
                name: {
                    "healthy": h.healthy,
                    "last_check": h.last_check,
                    "error": h.error,
                    "failure_count": self._failure_counts.get(name, 0),
                    "details": h.details,
                }
                for name, h in self._health.items()
            },
        }

    def is_healthy(self) -> bool:
        return all(h.healthy for h in self._health.values())

    # ------------------------------------------------------------------ #
    # Individual health checks
    # ------------------------------------------------------------------ #

    async def _check_download_manager(self) -> None:
        try:
            jobs = download_manager.list_jobs()
            active = len(download_manager._active)
            self._record_health(
                "download_manager",
                healthy=True,
                details={
                    "total_jobs": len(jobs),
                    "active_downloads": active,
                    "max_concurrent": download_manager._max_concurrent,
                    "running": download_manager._running,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log_error(exc, context="watchdog download_manager check")
            self._record_health("download_manager", healthy=False, error=str(exc))

    async def _check_websocket_manager(self) -> None:
        try:
            connections = len(getattr(ws_manager, "_connections", {}))
            self._record_health(
                "websocket_manager",
                healthy=True,
                details={"active_connections": connections},
            )
        except Exception as exc:  # noqa: BLE001
            log_error(exc, context="watchdog websocket_manager check")
            self._record_health("websocket_manager", healthy=False, error=str(exc))

    async def _check_cache(self) -> None:
        try:
            caches = {
                "search": search_cache.stats(),
                "metadata": metadata_cache.stats(),
                "lyrics": lyrics_cache.stats(),
                "source_health": source_health_cache.stats(),
            }
            all_ok = all(c.get("healthy", True) for c in caches.values())
            self._record_health(
                "cache",
                healthy=all_ok,
                details=caches,
            )
        except Exception as exc:  # noqa: BLE001
            log_error(exc, context="watchdog cache check")
            self._record_health("cache", healthy=False, error=str(exc))

    async def _check_plugins(self) -> None:
        try:
            plugins = plugin_manager.list_plugins() if hasattr(plugin_manager, "list_plugins") else {}
            loaded = len(plugins) if isinstance(plugins, dict) else 0
            self._record_health(
                "plugins",
                healthy=True,
                details={"loaded_plugins": loaded},
            )
        except Exception as exc:  # noqa: BLE001
            log_error(exc, context="watchdog plugins check")
            self._record_health("plugins", healthy=False, error=str(exc))

    async def _check_scheduler(self) -> None:
        try:
            running = getattr(scheduler, "_running", False)
            tasks = len(getattr(scheduler, "_tasks", {}))
            self._record_health(
                "scheduler",
                healthy=True,
                details={"running": running, "scheduled_tasks": tasks},
            )
        except Exception as exc:  # noqa: BLE001
            log_error(exc, context="watchdog scheduler check")
            self._record_health("scheduler", healthy=False, error=str(exc))

    async def _check_rate_limiter(self) -> None:
        try:
            self._record_health(
                "rate_limiter",
                healthy=True,
                details={"status": "active"},
            )
        except Exception as exc:  # noqa: BLE001
            log_error(exc, context="watchdog rate_limiter check")
            self._record_health("rate_limiter", healthy=False, error=str(exc))

    # ------------------------------------------------------------------ #
    # Recovery handlers
    # ------------------------------------------------------------------ #

    async def _recover_download_manager(self) -> None:
        if not download_manager._running:
            download_manager._running = True
            asyncio.create_task(download_manager._process_loop())
            logger.info("Watchdog recovered download_manager")

    async def _recover_websocket_manager(self) -> None:
        # WebSocket manager is stateless; nothing to recover
        logger.info("WebSocket manager health check passed (no recovery needed)")

    async def _recover_scheduler(self) -> None:
        if not getattr(scheduler, "_running", False):
            asyncio.create_task(scheduler.start())
            logger.info("Watchdog recovered scheduler")

    # ------------------------------------------------------------------ #
    # Main loops
    # ------------------------------------------------------------------ #

    async def _check_loop(self) -> None:
        """Periodically check all component health."""
        checks = {
            "download_manager": self._check_download_manager,
            "websocket_manager": self._check_websocket_manager,
            "cache": self._check_cache,
            "plugins": self._check_plugins,
            "scheduler": self._check_scheduler,
            "rate_limiter": self._check_rate_limiter,
        }

        while self._running:
            for name, check_fn in checks.items():
                try:
                    await check_fn()
                except Exception as exc:  # noqa: BLE001
                    log_error(exc, context=f"watchdog check {name}")
                    self._record_health(name, healthy=False, error=str(exc))
            await asyncio.sleep(self.check_interval)

    async def _recovery_loop(self) -> None:
        """Attempt recovery for unhealthy components."""
        while self._running:
            for name, health in self._health.items():
                if not health.healthy:
                    failures = self._failure_counts.get(name, 0)
                    if failures >= self.unhealthy_threshold:
                        handler = self._recovery_handlers.get(name)
                        if handler:
                            logger.warning(
                                "Watchdog attempting recovery for %s (failures=%d)",
                                name,
                                failures,
                            )
                            try:
                                if asyncio.iscoroutinefunction(handler):
                                    await handler()
                                else:
                                    handler()
                                self._failure_counts[name] = 0
                            except Exception as exc:  # noqa: BLE001
                                log_error(exc, context=f"watchdog recovery {name}")
            await asyncio.sleep(self.recovery_interval)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Start the watchdog background tasks."""
        if self._running:
            return
        self._running = True
        self.start_time = time.time()

        # Register default recovery handlers
        self.register_recovery("download_manager", self._recover_download_manager)
        self.register_recovery("websocket_manager", self._recover_websocket_manager)
        self.register_recovery("scheduler", self._recover_scheduler)

        self._task = asyncio.create_task(self._check_loop())
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        logger.info("Watchdog started (check_interval=%.1fs)", self.check_interval)

    async def stop(self) -> None:
        """Stop the watchdog background tasks."""
        self._running = False
        for task in (self._task, self._recovery_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("Watchdog stopped")


# Global watchdog instance
watchdog = Watchdog(
    check_interval=float(os.getenv("VIDEL_WATCHDOG_CHECK_INTERVAL", "30.0") if False else 30.0),
    recovery_interval=float(os.getenv("VIDEL_WATCHDOG_RECOVERY_INTERVAL", "60.0") if False else 60.0),
)
