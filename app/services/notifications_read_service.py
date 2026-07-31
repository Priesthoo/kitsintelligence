"""
Notification read-side service: listing, unread counts, mark-as-read, and
channel preference management. The write/delivery side lives in
app.workers.tasks.notification_tasks (enqueue_notification + the delivery
pipeline) -- this service is what the API layer talks to for everything a
logged-in user does with their own notification inbox.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError
from app.models.notifications import Notification
from app.repositories.notifications import NotificationPreferenceRepository, NotificationRepository


class NotificationReadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notifications = NotificationRepository(session)
        self.preferences = NotificationPreferenceRepository(session)

    async def list_for_user(
        self, user_id: uuid.UUID, *, page: int = 1, page_size: int = 50, unread_only: bool = False
    ) -> tuple[list[Notification], int]:
        offset = (page - 1) * page_size
        return await self.notifications.list_for_user(user_id, offset=offset, limit=page_size, unread_only=unread_only)

    async def get_stats(self, user_id: uuid.UUID) -> dict:
        unread = await self.notifications.count_unread(user_id)
        total = await self.notifications.count(user_id=user_id)
        return {"unread_count": unread, "total_count": total}

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        from app.db.base import utcnow

        notification = await self.notifications.get(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        notification.is_read = True
        notification.read_at = utcnow()
        await self.session.flush()
        return notification

    async def mark_read_bulk(self, user_id: uuid.UUID, notification_ids: list[uuid.UUID], mark_all: bool) -> int:
        return await self.notifications.mark_read_bulk(user_id, None if mark_all else notification_ids)

    async def delete(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
        notification = await self.notifications.get(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        await self.notifications.delete(notification, hard=True)

    async def list_preferences(self, user_id: uuid.UUID) -> list:
        return await self.preferences.list_for_user(user_id)

    async def update_preference(self, user_id: uuid.UUID, category: str, channel: str, is_enabled: bool):
        return await self.preferences.upsert(user_id, category, channel, is_enabled)