"""Repositories for Notification and NotificationPreference."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.db.base import utcnow
from app.models.notifications import Notification, NotificationPreference
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def list_for_user(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 50, unread_only: bool = False
    ) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        count_stmt = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)

        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
            count_stmt = count_stmt.where(Notification.is_read.is_(False))

        stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return list(result.scalars().all()), count_result.scalar_one()

    async def count_unread(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        return result.scalar_one()

    async def mark_read_bulk(self, user_id: uuid.UUID, notification_ids: list[uuid.UUID] | None) -> int:
        stmt = select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
        if notification_ids:
            stmt = stmt.where(Notification.id.in_(notification_ids))
        result = await self.session.execute(stmt)
        notifications = list(result.scalars().all())
        now = utcnow()
        for n in notifications:
            n.is_read = True
            n.read_at = now
        await self.session.flush()
        return len(notifications)


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    model = NotificationPreference

    async def list_for_user(self, user_id: uuid.UUID) -> list[NotificationPreference]:
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, user_id: uuid.UUID, category: str, channel: str, is_enabled: bool) -> NotificationPreference:
        existing = await self.get_or_none(user_id=user_id, category=category, channel=channel)
        if existing:
            existing.is_enabled = is_enabled
            await self.session.flush()
            return existing
        return await self.create(
            id=uuid.uuid4(), user_id=user_id, category=category, channel=channel, is_enabled=is_enabled
        )