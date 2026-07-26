"""
Connection manager for the WebSocket Gateway. Tracks live connections
per-user on this pod, and bridges Redis pub/sub -> local WebSocket sends so
that a message published from *any* API/worker pod (e.g. a notification
enqueued by a Celery task on a different machine) reaches a browser
connected to *this* pod. This fan-out pattern is what makes the gateway
horizontally scalable across replicas.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.cache import CacheManager
from app.core.logging import get_logger
from app.core.metrics import WEBSOCKET_CONNECTIONS_ACTIVE

logger = get_logger(__name__)


class ConnectionManager:
    """Singleton-per-process registry of active WebSocket connections, keyed by user_id."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)
        WEBSOCKET_CONNECTIONS_ACTIVE.inc()
        logger.info("websocket.connected", user_id=user_id, total_connections=self._count())

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        WEBSOCKET_CONNECTIONS_ACTIVE.dec()
        logger.info("websocket.disconnected", user_id=user_id, total_connections=self._count())

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """Sends to every local connection for this user. Returns count of successful sends."""
        sent = 0
        sockets = list(self._connections.get(user_id, set()))
        for ws in sockets:
            if ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_json(message)
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("websocket.send_failed", user_id=user_id, error=str(exc))
                    await self.disconnect(user_id, ws)
        return sent

    async def broadcast(self, message: dict) -> int:
        sent = 0
        for user_id in list(self._connections.keys()):
            sent += await self.send_to_user(user_id, message)
        return sent

    def _count(self) -> int:
        return sum(len(v) for v in self._connections.values())

    @property
    def active_connection_count(self) -> int:
        return self._count()


connection_manager = ConnectionManager()


class RedisSubscriberBridge:
    """
    Background task started at app startup: subscribes to per-user Redis
    pub/sub channels this pod cares about (dynamically, per connected user)
    and forwards messages to local WebSocket clients via ConnectionManager.
    """

    def __init__(self, cache: CacheManager) -> None:
        self.cache = cache
        self._tasks: dict[str, asyncio.Task] = {}

    async def subscribe_for_user(self, user_id: str) -> None:
        if user_id in self._tasks:
            return
        task = asyncio.create_task(self._listen(user_id))
        self._tasks[user_id] = task

    async def unsubscribe_for_user(self, user_id: str) -> None:
        task = self._tasks.pop(user_id, None)
        if task:
            task.cancel()

    async def _listen(self, user_id: str) -> None:
        channel = f"ws:user:{user_id}"
        try:
            async with self.cache.subscribe(channel) as pubsub:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    if not connection_manager._connections.get(user_id):
                        break
                    import orjson

                    payload = orjson.loads(message["data"])
                    await connection_manager.send_to_user(user_id, payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.error("websocket.redis_bridge_error", user_id=user_id, error=str(exc))


redis_bridge_registry: dict[int, RedisSubscriberBridge] = {}


def get_redis_bridge(cache: CacheManager) -> RedisSubscriberBridge:
    key = id(cache)
    if key not in redis_bridge_registry:
        redis_bridge_registry[key] = RedisSubscriberBridge(cache)
    return redis_bridge_registry[key]