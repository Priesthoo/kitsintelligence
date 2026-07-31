"""
Report request service: the API-facing half of the reporting pipeline.
Creating a report just inserts a QUEUED row and dispatches a Celery task
(see app.workers.tasks.report_tasks.generate_report) -- the request
returns instantly regardless of how long the underlying export takes.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError, ValidationError
from app.models.identity import User
from app.models.reports import Report, ReportFormat, ReportStatus
from app.repositories.report import ReportRepository
from app.schemas.reports import ReportRequestCreate
from app.services.audit_service import AuditService
from app.services.storage_services import StorageService

SUPPORTED_REPORT_TYPES: dict[str, list[str]] = {
    "audit_log_summary": ["csv", "json", "xlsx"],
    "alert_summary": ["csv", "json", "xlsx", "pdf"],
    "incident_summary": ["csv", "json", "xlsx", "pdf"],
    "risk_assessment_summary": ["csv", "json", "xlsx"],
}


class ReportRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ReportRepository(session)
        self.audit = AuditService(session)
        self.storage = StorageService()

    def list_available_types(self) -> list[dict]:
        descriptions = {
            "audit_log_summary": "Chronological export of organization audit trail entries.",
            "alert_summary": "Summary of alerts by severity, category, and status over a time range.",
            "incident_summary": "Summary of incidents including MTTR and priority breakdown.",
            "risk_assessment_summary": "Latest risk scores and factor breakdowns across all monitored profiles.",
        }
        return [
            {"report_type": rt, "description": descriptions[rt], "supported_formats": formats}
            for rt, formats in SUPPORTED_REPORT_TYPES.items()
        ]

    async def list_for_org(self, organization_id: uuid.UUID, *, page: int = 1, page_size: int = 50) -> tuple[list[Report], int]:
        offset = (page - 1) * page_size
        return await self.reports.list_for_org(organization_id, offset=offset, limit=page_size)

    async def get(self, report_id: uuid.UUID, organization_id: uuid.UUID) -> Report:
        report = await self.reports.get(report_id)
        if report is None or report.organization_id != organization_id:
            raise NotFoundError("Report not found")
        return report

    async def get_with_download_url(self, report_id: uuid.UUID, organization_id: uuid.UUID) -> tuple[Report, str | None]:
        report = await self.get(report_id, organization_id)
        url = None
        if report.status == ReportStatus.COMPLETED.value and report.file_key:
            url = await self.storage.generate_presigned_url(report.file_key)
        return report, url

    async def create(self, organization_id: uuid.UUID, payload: ReportRequestCreate, actor: User) -> Report:
        if payload.report_type not in SUPPORTED_REPORT_TYPES:
            raise ValidationError(
                f"Unknown report_type '{payload.report_type}'. "
                f"Available: {', '.join(SUPPORTED_REPORT_TYPES.keys())}"
            )
        if payload.format not in SUPPORTED_REPORT_TYPES[payload.report_type]:
            raise ValidationError(
                f"Format '{payload.format}' is not supported for report_type '{payload.report_type}'. "
                f"Supported: {', '.join(SUPPORTED_REPORT_TYPES[payload.report_type])}"
            )

        report = await self.reports.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            requested_by_id=actor.id,
            report_type=payload.report_type,
            format=payload.format,
            status=ReportStatus.QUEUED.value,
            parameters_json=payload.parameters_json,
        )

        from app.workers.tasks.report_tasks import generate_report

        generate_report.delay(str(report.id))

        await self.audit.record(
            action="report.request",
            resource_type="report",
            resource_id=str(report.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
            metadata={"report_type": payload.report_type, "format": payload.format},
        )
        return report

    async def delete(self, report_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        report = await self.get(report_id, organization_id)
        if report.file_key:
            await self.storage.delete(report.file_key)
        await self.reports.delete(report, hard=True)