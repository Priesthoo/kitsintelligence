"""Repository for Report queries."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.reports import Report
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    model = Report

    async def list_for_org(
        self, organization_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Report], int]:
        stmt = (
            select(Report)
            .where(Report.organization_id == organization_id)
            .order_by(Report.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count()).select_from(Report).where(Report.organization_id == organization_id)

        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return list(result.scalars().all()), count_result.scalar_one()