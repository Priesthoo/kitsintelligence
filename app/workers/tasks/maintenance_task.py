"""Periodic maintenance tasks: expired-token purge, stale-lock release, audit-log archival."""
from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from app.core.cache import get_cache_manager
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import db_session_scope
from app.models.identity import AuditLog, RefreshToken
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.maintenance_tasks.purge_expired_refresh_tokens")
def purge_expired_refresh_tokens() -> dict:
    return asyncio.run(_purge_expired_refresh_tokens())


async def _purge_expired_refresh_tokens() -> dict:
    async with db_session_scope() as session:
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < utcnow())
        result = await session.execute(stmt)
        deleted = result.rowcount or 0
    logger.info("maintenance.purge_expired_refresh_tokens", deleted=deleted)
    return {"deleted": deleted}


@celery_app.task(name="app.workers.tasks.maintenance_tasks.release_stale_locks")
def release_stale_locks() -> dict:
    return asyncio.run(_release_stale_locks())


async def _release_stale_locks() -> dict:
    cache = get_cache_manager()
    keys = await cache.keys_by_pattern("lock:*")
    released = 0
    for key in keys:
        ttl = await cache.ttl(key)
        if ttl == -1:  # no expiry set -- orphaned lock, force release
            await cache.delete(key)
            released += 1
    logger.info("maintenance.release_stale_locks", released=released)
    return {"released": released}


@celery_app.task(name="app.workers.tasks.maintenance_tasks.archive_old_audit_logs")
def archive_old_audit_logs(retention_days: int = 365) -> dict:
    return asyncio.run(_archive_old_audit_logs(retention_days))


async def _archive_old_audit_logs(retention_days: int) -> dict:
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=retention_days)
    async with db_session_scope() as session:
        stmt = select(AuditLog).where(AuditLog.created_at < cutoff).limit(5000)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await session.delete(row)
    logger.info("maintenance.archive_old_audit_logs", archived=len(rows))
    return {"archived": len(rows)}