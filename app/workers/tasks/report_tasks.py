"""
Async report generation. Reports are requested via API (queued instantly)
and rendered in the background so large exports never block a request
thread; the API polls / gets a WebSocket push when `status` flips to
COMPLETED, then downloads via a signed object-storage URL.
"""
from __future__ import annotations

import asyncio
import csv
import io
import uuid

from sqlalchemy import select
from openpyxl import Workbook

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import db_session_scope
from app.models.reports import Report, ReportFormat, ReportStatus
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.report_tasks.generate_report", bind=True, max_retries=1)
def generate_report(self, report_id: str) -> dict:  
    try:
        return asyncio.run(_generate_report(report_id))
    except Exception as exc:  
        logger.error("reports.generation_failed", report_id=report_id, error=str(exc))
        raise self.retry(exc=exc)


async def _generate_report(report_id: str) -> dict:
    async with db_session_scope() as session:
        stmt = select(Report).where(Report.id == uuid.UUID(report_id))
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()
        if report is None:
            logger.warning("reports.not_found", report_id=report_id)
            return {"status": "not_found"}

        report.status = ReportStatus.RUNNING.value
        report.started_at = utcnow()
        await session.flush()

        try:
            data_rows = await _collect_report_data(session, report)
            file_bytes, content_type = _render(report.format, report.report_type, data_rows)

            from app.services.storage_services import StorageService

            storage = StorageService()
            object_key = f"reports/{report.organization_id}/{report.id}.{report.format}"
            await storage.upload_bytes(object_key, file_bytes, content_type)

            report.file_key = object_key
            report.file_size_bytes = len(file_bytes)
            report.status = ReportStatus.COMPLETED.value
            report.completed_at = utcnow()

        except Exception as exc:  # noqa: BLE001
            report.status = ReportStatus.FAILED.value
            report.error_message = str(exc)[:2000]
            report.completed_at = utcnow()
            await session.flush()
            raise

        await session.flush()
        return {"status": report.status, "file_key": report.file_key}


async def _collect_report_data(session, report: Report) -> list[dict]:  
    """
    Pulls the underlying dataset for the requested report_type. Each report
    type maps to a query/aggregation; audit_log_summary shown as the
    reference implementation, additional types plug in the same way.
    """
    if report.report_type == "audit_log_summary":
        from app.models.identity import AuditLog

        stmt = select(AuditLog).where(AuditLog.organization_id == report.organization_id).limit(10000)
        if since := report.parameters_json.get("since"):
            stmt = stmt.where(AuditLog.created_at >= since)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id else "",
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    logger.warning("reports.unknown_type", report_type=report.report_type)
    return []


def _render(fmt: str, report_type: str, rows: list[dict]) -> tuple[bytes, str]:
    if fmt == ReportFormat.CSV.value:
        return _render_csv(rows), "text/csv"
    if fmt == ReportFormat.JSON.value:
        import orjson

        return orjson.dumps(rows), "application/json"
    if fmt == ReportFormat.XLSX.value:
        return _render_xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # PDF fallback: minimal text-based rendering without a heavy layout engine dependency.
    return _render_csv(rows), "text/csv"


def _render_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("no_data\n")
    return buffer.getvalue().encode("utf-8")


def _render_xlsx(rows: list[dict]) -> bytes:
   

    wb = Workbook()
    ws = wb.active
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()