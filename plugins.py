"""
Videl-Api Plugin System

Extensible source provider registry. Third-party or custom sources can be
registered as plugins and exposed through the standard /v1/search, /v1/info,
and /v1/download endpoints.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class SourcePlugin:
    id: str
    name: str
    type: str = "music"
    search_fn: Optional[Callable] = None
    info_fn: Optional[Callable] = None
    download_fn: Optional[Callable] = None
    capabilities: dict = field(default_factory=dict)
    enabled: bool = True
    module_path: Optional[str] = None


class PluginManager:
    """Registers and manages source plugins."""

    def __init__(self):
        self._plugins: dict[str, SourcePlugin] = {}

    def register(
        self,
        plugin_id: str,
        name: str,
        *,
        type: str = "music",
        search_fn: Optional[Callable] = None,
        info_fn: Optional[Callable] = None,
        download_fn: Optional[Callable] = None,
        capabilities: Optional[dict] = None,
        enabled: bool = True,
    ) -> None:
        self._plugins[plugin_id] = SourcePlugin(
            id=plugin_id,
            name=name,
            type=type,
            search_fn=search_fn,
            info_fn=info_fn,
            download_fn=download_fn,
            capabilities=capabilities or {},
            enabled=enabled,
        )

    def register_from_module(self, module_path: str, plugin_id: Optional[str] = None) -> None:
        """Load a plugin from a Python module path."""
        module = importlib.import_module(module_path)
        pid = plugin_id or getattr(module, "PLUGIN_ID", module_path.split(".")[-1])
        name = getattr(module, "PLUGIN_NAME", pid)
        ptype = getattr(module, "PLUGIN_TYPE", "music")
        caps = getattr(module, "PLUGIN_CAPABILITIES", {})
        search_fn = getattr(module, "search", None)
        info_fn = getattr(module, "info", None)
        download_fn = getattr(module, "download", None)
        self.register(
            pid, name, type=ptype, search_fn=search_fn, info_fn=info_fn,
            download_fn=download_fn, capabilities=caps,
        )
        self._plugins[pid].module_path = module_path

    def unregister(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            return True
        return False

    def enable(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].enabled = True
            return True
        return False

    def disable(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].enabled = False
            return True
        return False

    def get(self, plugin_id: str) -> Optional[SourcePlugin]:
        return self._plugins.get(plugin_id)

    def list(self, enabled_only: bool = False) -> list[dict]:
        out = []
        for p in self._plugins.values():
            if enabled_only and not p.enabled:
                continue
            out.append({
                "id": p.id,
                "name": p.name,
                "type": p.type,
                "enabled": p.enabled,
                "supports_search": p.search_fn is not None,
                "supports_info": p.info_fn is not None,
                "supports_download": p.download_fn is not None,
                "capabilities": p.capabilities,
                "module_path": p.module_path,
            })
        return out

    async def search(self, plugin_id: str, query: str, limit: int = 20) -> list[dict]:
        p = self._plugins.get(plugin_id)
        if not p or not p.enabled or not p.search_fn:
            return []
        try:
            if asyncio.iscoroutinefunction(p.search_fn):
                return await p.search_fn(query, limit=limit)
            return p.search_fn(query, limit=limit)
        except Exception:
            return []

    async def info(self, plugin_id: str, url: str) -> Optional[dict]:
        p = self._plugins.get(plugin_id)
        if not p or not p.enabled or not p.info_fn:
            return None
        try:
            if asyncio.iscoroutinefunction(p.info_fn):
                return await p.info_fn(url)
            return p.info_fn(url)
        except Exception:
            return None

    async def download(self, plugin_id: str, url: str, **kwargs) -> Optional[dict]:
        p = self._plugins.get(plugin_id)
        if not p or not p.enabled or not p.download_fn:
            return None
        try:
            if asyncio.iscoroutinefunction(p.download_fn):
                return await p.download_fn(url, **kwargs)
            return p.download_fn(url, **kwargs)
        except Exception:
            return None


# Global plugin manager
plugin_manager = PluginManager()