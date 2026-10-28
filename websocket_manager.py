"""
Videl-Api WebSocket Connection Manager

Manages WebSocket connections for real-time:
- Download progress updates
- Job status changes
- Notifications
- System alerts
- Broadcast messages
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("videl.websocket")


@dataclass
class Connection:
    websocket: WebSocket
    user_id: int
    connected_at: str
    channels: set[str] = field(default_factory=set)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts to channels."""

    def __init__(self):
        self._connections: dict[str, Connection] = {}
        self._channel_subs: dict[str, set[str]] = {}  # channel -> set of conn_ids
        self._lock = asyncio.Lock()

    async def connect(self, conn_id: str, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[conn_id] = Connection(
                websocket=websocket,
                user_id=user_id,
                connected_at=datetime.now(timezone.utc).isoformat(),
            )

    def _conn_channels(self, conn_id: str) -> set[str]:
        """Return channels this connection is subscribed to."""
        channels = set()
        for channel, conns in self._channel_subs.items():
            if conn_id in conns:
                channels.add(channel)
        return channels

    async def subscribe(self, conn_id: str, channel: str) -> None:
        async with self._lock:
            self._channel_subs.setdefault(channel, set()).add(conn_id)

    async def unsubscribe(self, conn_id: str, channel: Optional[str] = None) -> None:
        async with self._lock:
            if channel:
                self._channel_subs.get(channel, set()).discard(conn_id)
                if not self._channel_subs.get(channel):
                    self._channel_subs.pop(channel, None)
            else:
                for ch in list(self._channel_subs.keys()):
                    self._channel_subs[ch].discard(conn_id)
                    if not self._channel_subs[ch]:
                        self._channel_subs.pop(ch, None)

    async def disconnect(self, conn_id: str) -> None:
        async with self._lock:
            self._connections.pop(conn_id, None)
            await self.unsubscribe(conn_id)

    async def _send_json(self, websocket: WebSocket, data: dict) -> bool:
        try:
            await websocket.send_json(data)
            return True
        except Exception:
            return False

    async def broadcast_to_channel(self, channel: str, data: dict) -> int:
        """Send a message to all connections subscribed to a channel."""
        sent = 0
        dead: list[str] = []
        async with self._lock:
            conn_ids = list(self._channel_subs.get(channel, set()))
        for cid in conn_ids:
            async with self._lock:
                conn = self._connections.get(cid)
            if not conn:
                dead.append(cid)
                continue
            ok = await self._send_json(conn.websocket, data)
            if ok:
                sent += 1
            else:
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)
        return sent

    async def send_to_user(self, user_id: int, data: dict) -> int:
        """Send a message to all connections belonging to a user."""
        sent = 0
        dead: list[str] = []
        async with self._lock:
            conns = [
                (cid, c) for cid, c in self._connections.items()
                if c.user_id == user_id
            ]
        for cid, conn in conns:
            ok = await self._send_json(conn.websocket, data)
            if ok:
                sent += 1
            else:
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)
        return sent

    async def broadcast_all(self, data: dict) -> int:
        """Broadcast to all connected clients."""
        sent = 0
        dead: list[str] = []
        async with self._lock:
            conns = list(self._connections.items())
        for cid, conn in conns:
            ok = await self._send_json(conn.websocket, data)
            if ok:
                sent += 1
            else:
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)
        return sent

    def get_connection_count(self) -> int:
        return len(self._connections)

    def get_user_connections(self, user_id: int) -> int:
        return sum(
            1 for c in self._connections.values() if c.user_id == user_id
        )

    def get_channel_subscribers(self, channel: str) -> int:
        return len(self._channel_subs.get(channel, set()))

    def stats(self) -> dict:
        return {
            "total_connections": len(self._connections),
            "channels": len(self._channel_subs),
            "channel_subscribers": {
                ch: len(conns) for ch, conns in self._channel_subs.items()
            },
        }


# Global WebSocket manager
ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# WebSocket handler helper
# ---------------------------------------------------------------------------

async def handle_websocket(websocket: WebSocket, user_id: int, conn_id: str) -> None:
    """Main WebSocket handler loop. Registers connection and listens for messages."""
    await ws_manager.connect(conn_id, websocket, user_id)
    # Subscribe to user-specific channel
    await ws_manager.subscribe(conn_id, f"user:{user_id}")
    # Subscribe to general notifications
    await ws_manager.subscribe(conn_id, "notifications")

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "ping")

            if action == "subscribe":
                channel = data.get("channel", "")
                if channel:
                    await ws_manager.subscribe(conn_id, channel)
                    await ws_manager._send_json(websocket, {
                        "type": "subscribed", "channel": channel
                    })
            elif action == "unsubscribe":
                channel = data.get("channel", "")
                if channel:
                    await ws_manager.unsubscribe(conn_id, channel)
                    await ws_manager._send_json(websocket, {
                        "type": "unsubscribed", "channel": channel
                    })
            elif action == "ping":
                await ws_manager._send_json(websocket, {
                    "type": "pong", "timestamp": data.get("timestamp", 0)
                })
            else:
                await ws_manager._send_json(websocket, {
                    "type": "error", "message": f"Unknown action: {action}"
                })
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"WebSocket error for user {user_id}: {exc}")
    finally:
        await ws_manager.disconnect(conn_id)