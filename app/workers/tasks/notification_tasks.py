"""
Notification delivery pipeline. `process_pending_notifications` runs every
30s via beat, picks up due/pending notifications, checks per-user channel
preferences, and dispatches to the right transport. Email/SMS transports
are stubbed behind a clean interface so real providers (SES, Twilio, etc.)
can be swapped in via config without touching task logic.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select

from app.core.cache import get_cache_manager
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import db_session_scope
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
)
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

BATCH_SIZE = 200


@celery_app.task(name="app.workers.tasks.notification_tasks.process_pending_notifications")
def process_pending_notifications() -> dict:
    return asyncio.run(_process_pending_notifications())


async def _process_pending_notifications() -> dict:
    cache = get_cache_manager()
    async with cache.acquire_lock("notifications:dispatch_sweep", timeout=60, blocking_timeout=1) as acquired:
        if not acquired:
            return {"skipped": True}

        now = utcnow()
        sent, failed = 0, 0

        async with db_session_scope() as session:
            stmt = (
                select(Notification)
                .where(
                    Notification.status == NotificationStatus.PENDING.value,
                    (Notification.scheduled_for.is_(None)) | (Notification.scheduled_for <= now),
                )
                .limit(BATCH_SIZE)
            )
            result = await session.execute(stmt)
            pending = list(result.scalars().all())

            for notification in pending:
                enabled = await _is_channel_enabled(session, notification.user_id, notification.category, notification.channel)
                if not enabled:
                    notification.status = NotificationStatus.FAILED.value
                    notification.error_message = "Channel disabled by user preference"
                    failed += 1
                    continue

                ok = await _dispatch(notification)
                if ok:
                    notification.status = NotificationStatus.SENT.value
                    notification.sent_at = utcnow()
                    sent += 1
                else:
                    notification.status = NotificationStatus.FAILED.value
                    notification.error_message = "Delivery transport error"
                    failed += 1

                # Fan out to WebSocket subscribers immediately for in-app notifications
                if notification.channel == NotificationChannel.IN_APP.value:
                    await cache.publish(
                        f"ws:user:{notification.user_id}",
                        {
                            "type": "notification",
                            "id": str(notification.id),
                            "title": notification.title,
                            "body": notification.body,
                            "category": notification.category,
                        },
                    )

        logger.info("notifications.sweep_completed", sent=sent, failed=failed)
        return {"sent": sent, "failed": failed}


async def _is_channel_enabled(session, user_id: uuid.UUID, category: str, channel: str) -> bool:  # noqa: ANN001
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,
        NotificationPreference.category == category,
        NotificationPreference.channel == channel,
    )
    result = await session.execute(stmt)
    pref = result.scalar_one_or_none()
    return pref.is_enabled if pref is not None else True  # default: opted in


async def _dispatch(notification: Notification) -> bool:
    """Routes to the appropriate transport. In-app requires no external call (cache publish handles it)."""
    if notification.channel == NotificationChannel.IN_APP.value:
        return True
    if notification.channel == NotificationChannel.EMAIL.value:
        return await _send_email(notification)
    if notification.channel == NotificationChannel.SMS.value:
        return await _send_sms(notification)
    if notification.channel == NotificationChannel.WEBHOOK.value:
        return await _send_webhook(notification)
    logger.warning("notifications.unknown_channel", channel=notification.channel)
    return False


async def _send_email(notification: Notification) -> bool:
    # Provider integration point (SES/SendGrid/etc.) -- logged as a successful
    # dry-run send here since no SMTP/API credentials are configured by default.
    logger.info("notifications.email_dispatch", notification_id=str(notification.id))
    return True


async def _send_sms(notification: Notification) -> bool:
    logger.info("notifications.sms_dispatch", notification_id=str(notification.id))
    return True


async def _send_webhook(notification: Notification) -> bool:
    import httpx

    url = notification.metadata_json.get("webhook_url")
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json={"title": notification.title, "body": notification.body, "category": notification.category},
            )
            response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("notifications.webhook_failed", error=str(exc))
        return False


@celery_app.task(name="app.workers.tasks.notification_tasks.enqueue_notification")
def enqueue_notification(
    user_id: str, organization_id: str, category: str, channel: str, title: str, body: str, metadata: dict | None = None
) -> str:
    return asyncio.run(_enqueue_notification(user_id, organization_id, category, channel, title, body, metadata))


async def _enqueue_notification(
    user_id: str, organization_id: str, category: str, channel: str, title: str, body: str, metadata: dict | None
) -> str:
    async with db_session_scope() as session:
        notification = Notification(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            organization_id=uuid.UUID(organization_id),
            category=category,
            channel=channel,
            status=NotificationStatus.PENDING.value,
            title=title,
            body=body,
            metadata_json=metadata or {},
        )
        session.add(notification)
        await session.flush()
        return str(notification.id)