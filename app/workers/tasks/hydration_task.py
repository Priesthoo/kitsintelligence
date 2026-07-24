"""
Celery tasks driving the Hydration Engine. `hydrate_all_active_sources` is
the beat-scheduled entrypoint that fans out to a per-source task so a
single slow/failing connector cannot block the rest of the fleet.
"""
from __future__ import annotations

import asyncio
import uuid

from app.core.cache import get_cache_manager
from app.core.logging import get_logger
from app.db.session import db_session_scope
from app.services.hydration_service import DataSourceRepository, HydrationEngine
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.hydration_tasks.hydrate_all_active_sources")
def hydrate_all_active_sources() -> dict:
    return asyncio.run(_hydrate_all_active_sources())


async def _hydrate_all_active_sources() -> dict:
    cache = get_cache_manager()
    async with cache.acquire_lock("hydration:global_sweep", timeout=280, blocking_timeout=1) as acquired:
        if not acquired:
            logger.info("hydration.sweep_skipped_already_running")
            return {"skipped": True}

        async with db_session_scope() as session:
            engine = HydrationEngine(session, cache)
            sources_repo = DataSourceRepository(session)
            due_sources = await sources_repo.list_active_due()

        logger.info("hydration.sweep_started", due_count=len(due_sources))

        dispatched = 0
        for source in due_sources:
            hydrate_single_source.delay(str(source.id))
            dispatched += 1

        return {"dispatched": dispatched}


@celery_app.task(
    name="app.workers.tasks.hydration_tasks.hydrate_single_source",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def hydrate_single_source(self, data_source_id: str) -> dict:  
    try:
        return asyncio.run(_hydrate_single_source(data_source_id))
    except Exception as exc:  
        logger.error("hydration.task_failed", data_source_id=data_source_id, error=str(exc))
        raise self.retry(exc=exc)


async def _hydrate_single_source(data_source_id: str) -> dict:
    cache = get_cache_manager()
    async with db_session_scope() as session:
        engine = HydrationEngine(session, cache)
        sources_repo = DataSourceRepository(session)
        source = await sources_repo.get(uuid.UUID(data_source_id))
        if source is None:
            logger.warning("hydration.source_not_found", data_source_id=data_source_id)
            return {"status": "not_found"}

        run = await engine.run_for_source(source)
        return {
            "status": run.status,
            "records_written": run.records_written,
            "duration_ms": run.duration_ms,
        }


@celery_app.task(name="app.workers.tasks.hydration_tasks.hydrate_source_now")
def hydrate_source_now(data_source_id: str) -> dict:
    """Manual on-demand trigger, invoked from the Data Sources admin API 'sync now' action."""
    return asyncio.run(_hydrate_single_source(data_source_id))