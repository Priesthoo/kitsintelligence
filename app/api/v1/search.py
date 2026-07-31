"""Cross-entity search endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permissions
from app.models.identity import User
from app.services.search_services import SearchService

router = APIRouter(tags=["Search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=2, max_length=200),
    user: User = Depends(require_permissions("search:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SearchService(db)
    return await service.search(user.organization_id, q)