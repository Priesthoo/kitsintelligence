"""Repository for Alert queries: filtered listing, stats aggregation."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.db.base import utcnow
from app.models.alerts import Alert, AlertStatus
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    model = Alert

    async def list_filtered(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Alert], int]:
        stmt = select(Alert).where(Alert.organization_id == organization_id)
        count_stmt = select(func.count()).select_from(Alert).where(Alert.organization_id == organization_id)

        if status:
            stmt = stmt.where(Alert.status == status)
            count_stmt = count_stmt.where(Alert.status == status)
        if severity:
            stmt = stmt.where(Alert.severity == severity)
            count_stmt = count_stmt.where(Alert.severity == severity)
        if category:
            stmt = stmt.where(Alert.category == category)
            count_stmt = count_stmt.where(Alert.category == category)

        stmt = stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return list(result.scalars().all()), count_result.scalar_one()

    async def get_stats(self, organization_id: uuid.UUID) -> dict:
        open_count_result = await self.session.execute(
            select(func.count()).select_from(Alert).where(
                Alert.organization_id == organization_id, Alert.status == AlertStatus.OPEN.value
            )
        )
        ack_count_result = await self.session.execute(
            select(func.count()).select_from(Alert).where(
                Alert.organization_id == organization_id, Alert.status == AlertStatus.ACKNOWLEDGED.value
            )
        )
        cutoff = utcnow() - timedelta(days=7)
        resolved_result = await self.session.execute(
            select(func.count()).select_from(Alert).where(
                Alert.organization_id == organization_id,
                Alert.status == AlertStatus.RESOLVED.value,
                Alert.resolved_at >= cutoff,
            )
        )

        severity_result = await self.session.execute(
            select(Alert.severity, func.count())
            .where(Alert.organization_id == organization_id, Alert.status != AlertStatus.DISMISSED.value)
            .group_by(Alert.severity)
        )
        category_result = await self.session.execute(
            select(Alert.category, func.count())
            .where(Alert.organization_id == organization_id, Alert.status != AlertStatus.DISMISSED.value)
            .group_by(Alert.category)
        )

        return {
            "total_open": open_count_result.scalar_one(),
            "total_acknowledged": ack_count_result.scalar_one(),
            "total_resolved_last_7d": resolved_result.scalar_one(),
            "by_severity": dict(severity_result.all()),
            "by_category": dict(category_result.all()),
        }