"""Reports endpoints: request generation, list, poll status, download."""
from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permissions
from app.models.identity import User
from app.schemas.identity import PaginatedResponse
from app.schemas.reports import ReportRead, ReportRequestCreate, ReportTypeInfo, ReportWithDownloadUrl
from app.services.report_request_service import ReportRequestService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/types", response_model=list[ReportTypeInfo])
async def list_report_types(_: User = Depends(require_permissions("reports:read"))) -> list:
    service = ReportRequestService.__new__(ReportRequestService)  # no DB needed for static catalog
    return service.list_available_types()


@router.get("", response_model=PaginatedResponse)
async def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permissions("reports:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ReportRequestService(db)
    items, total = await service.list_for_org(user.organization_id, page=page, page_size=page_size)
    return {
        "items": [ReportRead.model_validate(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.get("/{report_id}", response_model=ReportWithDownloadUrl)
async def get_report(
    report_id: uuid.UUID,
    user: User = Depends(require_permissions("reports:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ReportRequestService(db)
    report, url = await service.get_with_download_url(report_id, user.organization_id)
    data = ReportRead.model_validate(report).model_dump()
    data["download_url"] = url
    return data


@router.post("", response_model=ReportRead, status_code=status.HTTP_202_ACCEPTED)
async def request_report(
    payload: ReportRequestCreate,
    actor: User = Depends(require_permissions("reports:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = ReportRequestService(db)
    return await service.create(actor.organization_id, payload, actor)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: uuid.UUID,
    user: User = Depends(require_permissions("reports:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ReportRequestService(db)
    await service.delete(report_id, user.organization_id)