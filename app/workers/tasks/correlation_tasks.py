"""Celery task running the correlation pass periodically across all organizations."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.cache import get_cache_manager
from app.core.logging import get_logger
from app.db.session import db_session_scope
from app.models.identity import Organization
from app.services.correlation_service import CorrelationService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.correlation_tasks.run_correlation_for_all_orgs")
def run_correlation_for_all_orgs() -> dict:
    return asyncio.run(_run_correlation_for_all_orgs())


async def _run_correlation_for_all_orgs() -> dict:
    cache = get_cache_manager()
    async with cache.acquire_lock("correlation:global_sweep", timeout=280, blocking_timeout=1) as acquired:
        if not acquired:
            return {"skipped": True}

        total_clusters = 0
        async with db_session_scope() as session:
            orgs_result = await session.execute(select(Organization).where(Organization.is_active.is_(True)))
            orgs = list(orgs_result.scalars().all())

            for org in orgs:
                service = CorrelationService(session, cache)
                result = await service.run_correlation_pass(org.id)
                total_clusters += result["clusters_created"]

        logger.info("correlation.sweep_completed", orgs_scanned=len(orgs), clusters_created=total_clusters)
        return {"orgs_scanned": len(orgs), "clusters_created": total_clusters}