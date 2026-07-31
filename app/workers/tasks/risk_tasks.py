"""Periodic recalculation of every active risk profile across all organizations."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.cache import get_cache_manager
from app.core.logging import get_logger
from app.db.session import db_session_scope
from app.models.risk_assessment import RiskProfile
from app.services.risk_assessment_service import RiskAssessmentService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.risk_tasks.recalculate_all_risk_profiles")
def recalculate_all_risk_profiles() -> dict:
    return asyncio.run(_recalculate_all_risk_profiles())


async def _recalculate_all_risk_profiles() -> dict:
    cache = get_cache_manager()
    async with cache.acquire_lock("risk_assessment:global_sweep", timeout=280, blocking_timeout=1) as acquired:
        if not acquired:
            return {"skipped": True}

        recalculated = 0
        async with db_session_scope() as session:
            service = RiskAssessmentService(session, cache)
            result = await session.execute(select(RiskProfile).where(RiskProfile.is_active.is_(True)))
            profiles = list(result.scalars().all())

            for profile in profiles:
                await service.recalculate(profile.id, profile.organization_id)
                recalculated += 1

        logger.info("risk_assessment.sweep_completed", recalculated=recalculated)
        return {"recalculated": recalculated}