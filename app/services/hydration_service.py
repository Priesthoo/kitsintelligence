"""
Hydration Engine: orchestrates a single connector run end-to-end —
credential decryption, circuit-breaker check, connector invocation,
persistence of the run audit record, and writing results into the cache
so API routes can serve them instantly.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorRegistry
from app.core.cache import CacheManager
from app.core.logging import get_logger
from app.core.metrics import HYDRATION_JOBS_TOTAL, HYDRATION_JOB_DURATION_SECONDS
from app.db.base import utcnow
from app.exceptions.base import ConnectorError
from app.models.data_sources import DataSource, DataSourceStatus, HydrationRun, HydrationRunStatus
from app.repositories.base import BaseRepository

logger = get_logger(__name__)

CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_OPEN_DURATION_MINUTES = 10
CACHE_KEY_PREFIX = "hydrated"


class DataSourceRepository(BaseRepository[DataSource]):
    model = DataSource

    async def list_active_due(self) -> list[DataSource]:
        from sqlalchemy import select

        now = utcnow()
        stmt = select(DataSource).where(
            DataSource.is_deleted.is_(False),
            DataSource.status == DataSourceStatus.ACTIVE.value,
        )
        result = await self.session.execute(stmt)
        sources = list(result.scalars().all())
        due = []
        for s in sources:
            if s.is_circuit_open:
                continue
            if s.last_synced_at is None:
                due.append(s)
                continue
            elapsed = (now - s.last_synced_at).total_seconds()
            if elapsed >= s.sync_interval_seconds:
                due.append(s)
        return due


class HydrationEngine:
    def __init__(self, session: AsyncSession, cache: CacheManager) -> None:
        self.session = session
        self.cache = cache
        self.sources = DataSourceRepository(session)

    async def run_for_source(self, source: DataSource) -> HydrationRun:
        started_at = utcnow()
        run = HydrationRun(
            id=uuid.uuid4(),
            data_source_id=source.id,
            status=HydrationRunStatus.RUNNING.value,
            started_at=started_at,
        )
        self.session.add(run)
        await self.session.flush()

        start_perf = time.perf_counter()
        try:
            connector_cls = ConnectorRegistry.get(source.connector_key)
            credentials = await self._decrypt_credentials(source)

            async with connector_cls(source.config_json, credentials) as connector:
                result = await connector.fetch_with_retry()

            await self._write_to_cache(source, result.records)

            run.status = HydrationRunStatus.SUCCESS.value
            run.records_fetched = result.raw_count
            run.records_written = len(result.records)
            source.consecutive_failures = 0
            source.circuit_open_until = None
            source.last_success_at = utcnow()

            HYDRATION_JOBS_TOTAL.labels(source=source.slug, status="success").inc()

        except Exception as exc:  # noqa: BLE001
            run.status = HydrationRunStatus.FAILED.value
            run.error_message = str(exc)[:2000]
            source.consecutive_failures += 1

            if source.consecutive_failures >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                source.circuit_open_until = utcnow() + timedelta(minutes=CIRCUIT_BREAKER_OPEN_DURATION_MINUTES)
                source.status = DataSourceStatus.ERROR.value
                logger.error(
                    "hydration.circuit_breaker_opened",
                    source=source.slug,
                    failures=source.consecutive_failures,
                )

            HYDRATION_JOBS_TOTAL.labels(source=source.slug, status="failed").inc()
            logger.error("hydration.run_failed", source=source.slug, error=str(exc))

        finally:
            duration = time.perf_counter() - start_perf
            run.finished_at = utcnow()
            run.duration_ms = int(duration * 1000)
            source.last_synced_at = utcnow()
            HYDRATION_JOB_DURATION_SECONDS.labels(source=source.slug).observe(duration)
            await self.session.flush()

        return run

    async def _decrypt_credentials(self, source: DataSource) -> dict[str, str]:
        from app.utils.crypto import decrypt_value

        creds: dict[str, str] = {}
        for cred in source.credentials:
            creds[cred.credential_key] = decrypt_value(cred.encrypted_value)
        return creds

    async def _write_to_cache(self, source: DataSource, records: list[dict]) -> None:
        cache_key = f"{CACHE_KEY_PREFIX}:{source.category}:{source.slug}"
        payload = {
            "source_slug": source.slug,
            "category": source.category,
            "hydrated_at": utcnow().isoformat(),
            "record_count": len(records),
            "records": records,
        }
        ttl = max(source.sync_interval_seconds * 3, 300)
        await self.cache.set_json(cache_key, payload, ttl_seconds=ttl)
        await self.cache.zadd("hydration:recency", cache_key, time.time())

    async def run_all_due(self) -> dict:
        due_sources = await self.sources.list_active_due()
        results = {"total_due": len(due_sources), "success": 0, "failed": 0}
        for source in due_sources:
            run = await self.run_for_source(source)
            if run.status == HydrationRunStatus.SUCCESS.value:
                results["success"] += 1
            else:
                results["failed"] += 1
        return results