"""
WebSocket Gateway endpoint. Clients authenticate via a short-lived JWT
passed as a query param (browsers cannot set custom headers on the
WebSocket handshake), then receive real-time pushes: notifications, alert
updates, hydration-completion events, and report-ready signals — all
without polling.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.cache import get_cache_manager
from app.core.logging import get_logger
from app.core.security import TokenType, decode_token
from app.db.session import AsyncSessionFactory
from app.exceptions.base import AuthenticationError
from app.repositories.identity import UserRepository
from app.websockets.manager import connection_manager, get_redis_bridge

logger = get_logger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
        user_id = payload["sub"]
    except AuthenticationError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return

    async with AsyncSessionFactory() as session:
        user = await UserRepository(session).get(uuid.UUID(user_id))
        if user is None or user.status != "active":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not active")
            return

    cache = get_cache_manager()
    bridge = get_redis_bridge(cache)

    await connection_manager.connect(user_id, websocket)
    await bridge.subscribe_for_user(user_id)

    try:
        await websocket.send_json({"type": "connected", "user_id": user_id})
        while True:
            # Clients may send lightweight pings/acks; the gateway itself is push-only
            # for domain events, so incoming messages are just liveness signals.
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("websocket.client_disconnected", user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("websocket.unexpected_error", user_id=user_id, error=str(exc))
    finally:
        await connection_manager.disconnect(user_id, websocket)
        if not connection_manager._connections.get(user_id):
            await bridge.unsubscribe_for_user(user_id)