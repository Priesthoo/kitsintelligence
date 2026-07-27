
"""
Connection manager for the WebSocket Gateway. Tracks live connections
per-user AND per-organization on this pod, and bridges Redis pub/sub ->
local WebSocket sends so a message published from *any* API/worker pod
(a notification, an org-wide alert, a hydration-completion event) reaches
every relevant browser connected to *this* pod. This fan-out pattern is
what makes the gateway horizontally scalable across replicas.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.cache import CacheManager
from app.core.logging import get_logger
from app.core.metrics import WEBSOCKET_CONNECTIONS_ACTIVE

logger = get_logger(__name__)


class ConnectionManager:
    """Singleton-per-process registry of active WebSocket connections, keyed by user_id and org_id."""

    def __init__(self) -> None:
        self._user_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._org_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._connection_org: dict[WebSocket, str] = {}
        self._connection_user: dict[WebSocket, str] = {}
        self._org_member_counts: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, org_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._user_connections[user_id].add(websocket)
            self._org_connections[org_id].add(websocket)
            self._connection_org[websocket] = org_id
            self._connection_user[websocket] = user_id
            self._org_member_counts[org_id] += 1
        WEBSOCKET_CONNECTIONS_ACTIVE.inc()
        logger.info("websocket.connected", user_id=user_id, org_id=org_id, total_connections=self._count())

    async def disconnect(self, websocket: WebSocket) -> tuple[str | None, str | None]:
        async with self._lock:
            user_id = self._connection_user.pop(websocket, None)
            org_id = self._connection_org.pop(websocket, None)
            if user_id is not None:
                self._user_connections[user_id].discard(websocket)
                if not self._user_connections[user_id]:
                    del self._user_connections[user_id]
            if org_id is not None:
                self._org_connections[org_id].discard(websocket)
                self._org_member_counts[org_id] = max(0, self._org_member_counts[org_id] - 1)
                if not self._org_connections[org_id]:
                    del self._org_connections[org_id]
                    self._org_member_counts.pop(org_id, None)
        WEBSOCKET_CONNECTIONS_ACTIVE.dec()
        logger.info("websocket.disconnected", user_id=user_id, org_id=org_id, total_connections=self._count())
        return user_id, org_id

    async def send_to_user(self, user_id: str, message: dict) -> int:
        sent = 0
        sockets = list(self._user_connections.get(user_id, set()))
        for ws in sockets:
            if ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_json(message)
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("websocket.send_failed", user_id=user_id, error=str(exc))
                    await self.disconnect(ws)
        return sent

    async def send_to_org(self, org_id: str, message: dict) -> int:
        sent = 0
        sockets = list(self._org_connections.get(org_id, set()))
        for ws in sockets:
            if ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_json(message)
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("websocket.send_failed", org_id=org_id, error=str(exc))
                    await self.disconnect(ws)
        return sent

    async def broadcast(self, message: dict) -> int:
        sent = 0
        for user_id in list(self._user_connections.keys()):
            sent += await self.send_to_user(user_id, message)
        return sent

    def is_first_connection_for_org(self, org_id: str) -> bool:
        return self._org_member_counts.get(org_id, 0) == 0

    def has_no_connections_for_org(self, org_id: str) -> bool:
        return self._org_member_counts.get(org_id, 0) == 0

    def has_no_connections_for_user(self, user_id: str) -> bool:
        return user_id not in self._user_connections

    def _count(self) -> int:
        return sum(len(v) for v in self._user_connections.values())

    @property
    def active_connection_count(self) -> int:
        return self._count()


connection_manager = ConnectionManager()


class RedisSubscriberBridge:
    """
    Background task registry: subscribes to per-user AND per-org Redis
    pub/sub channels this pod has active connections for, forwarding
    messages to the right local WebSocket clients via ConnectionManager.
    """

    def __init__(self, cache: CacheManager) -> None:
        self.cache = cache
        self._user_tasks: dict[str, asyncio.Task] = {}
        self._org_tasks: dict[str, asyncio.Task] = {}

    async def subscribe_for_user(self, user_id: str) -> None:
        if user_id not in self._user_tasks:
            self._user_tasks[user_id] = asyncio.create_task(self._listen_user(user_id))

    async def unsubscribe_for_user(self, user_id: str) -> None:
        task = self._user_tasks.pop(user_id, None)
        if task:
            task.cancel()

    async def subscribe_for_org(self, org_id: str) -> None:
        if org_id not in self._org_tasks:
            self._org_tasks[org_id] = asyncio.create_task(self._listen_org(org_id))

    async def unsubscribe_for_org(self, org_id: str) -> None:
        task = self._org_tasks.pop(org_id, None)
        if task:
            task.cancel()

    async def _listen_user(self, user_id: str) -> None:
        channel = f"ws:user:{user_id}"
        try:
            async with self.cache.subscribe(channel) as pubsub:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    if connection_manager.has_no_connections_for_user(user_id):
                        break
                    import orjson

                    payload = orjson.loads(message["data"])
                    await connection_manager.send_to_user(user_id, payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.error("websocket.redis_bridge_user_error", user_id=user_id, error=str(exc))

    async def _listen_org(self, org_id: str) -> None:
        channel = f"ws:org:{org_id}"
        try:
            async with self.cache.subscribe(channel) as pubsub:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    if connection_manager.has_no_connections_for_org(org_id):
                        break
                    import orjson

                    payload = orjson.loads(message["data"])
                    await connection_manager.send_to_org(org_id, payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.error("websocket.redis_bridge_org_error", org_id=org_id, error=str(exc))


redis_bridge_registry: dict[int, RedisSubscriberBridge] = {}


def get_redis_bridge(cache: CacheManager) -> RedisSubscriberBridge:
    key = id(cache)
    if key not in redis_bridge_registry:
        redis_bridge_registry[key] = RedisSubscriberBridge(cache)
    return redis_bridge_registry[key]