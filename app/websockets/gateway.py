"""
WebSocket Gateway endpoint. Clients authenticate via a short-lived JWT
passed as a query param (browsers cannot set custom headers on the
WebSocket handshake), then receive real-time pushes: notifications, org-wide
alert broadcasts, hydration-completion events, and report-ready signals —
all without polling.
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
        org_id = str(user.organization_id)

    cache = get_cache_manager()
    bridge = get_redis_bridge(cache)

    await connection_manager.connect(user_id, org_id, websocket)
    await bridge.subscribe_for_user(user_id)
    await bridge.subscribe_for_org(org_id)

    try:
        await websocket.send_json({"type": "connected", "user_id": user_id, "organization_id": org_id})
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("websocket.client_disconnected", user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("websocket.unexpected_error", user_id=user_id, error=str(exc))
    finally:
        disconnected_user_id, disconnected_org_id = await connection_manager.disconnect(websocket)
        if disconnected_user_id and connection_manager.has_no_connections_for_user(disconnected_user_id):
            await bridge.unsubscribe_for_user(disconnected_user_id)
        if disconnected_org_id and connection_manager.has_no_connections_for_org(disconnected_org_id):
            await bridge.unsubscribe_for_org(disconnected_org_id)