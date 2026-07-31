"""Risk Assessment endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_db, require_permissions
from app.core.cache import CacheManager
from app.models.identity import User
from app.schemas.risk_assessment import (
    RecalculateResponse,
    RiskProfileCreate,
    RiskProfileDetail,
    RiskProfileRead,
    RiskProfileUpdate,
)
from app.services.risk_assessment_service import RiskAssessmentService

router = APIRouter(prefix="/risk-assessment", tags=["Risk Assessment"])


def _to_read(profile) -> dict:  
    latest = profile.scores[0] if profile.scores else None
    return {
        "id": profile.id,
        "organization_id": profile.organization_id,
        "name": profile.name,
        "subject_type": profile.subject_type,
        "description": profile.description,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "monitored_radius_km": profile.monitored_radius_km,
        "monitored_categories": profile.monitored_categories,
        "is_active": profile.is_active,
        "created_at": profile.created_at,
        "latest_score": latest,
    }


def _to_detail(profile) -> dict:  
    base = _to_read(profile)
    base["score_history"] = profile.scores
    return base


@router.get("", response_model=list[RiskProfileRead])
async def list_risk_profiles(
    user: User = Depends(require_permissions("risk_assessment:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> list:
    service = RiskAssessmentService(db, cache)
    profiles = await service.list_for_org(user.organization_id)
    return [_to_read(p) for p in profiles]


@router.get("/{profile_id}", response_model=RiskProfileDetail)
async def get_risk_profile(
    profile_id: uuid.UUID,
    user: User = Depends(require_permissions("risk_assessment:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = RiskAssessmentService(db, cache)
    profile = await service.get(profile_id, user.organization_id)
    return _to_detail(profile)


@router.post("", response_model=RiskProfileDetail, status_code=status.HTTP_201_CREATED)
async def create_risk_profile(
    payload: RiskProfileCreate,
    actor: User = Depends(require_permissions("risk_assessment:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = RiskAssessmentService(db, cache)
    profile = await service.create(actor.organization_id, payload)
    return _to_detail(profile)


@router.patch("/{profile_id}", response_model=RiskProfileRead)
async def update_risk_profile(
    profile_id: uuid.UUID,
    payload: RiskProfileUpdate,
    actor: User = Depends(require_permissions("risk_assessment:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = RiskAssessmentService(db, cache)
    profile = await service.update(profile_id, actor.organization_id, payload)
    return _to_read(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_risk_profile(
    profile_id: uuid.UUID,
    actor: User = Depends(require_permissions("risk_assessment:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> None:
    service = RiskAssessmentService(db, cache)
    await service.delete(profile_id, actor.organization_id)


@router.post("/{profile_id}/recalculate", response_model=RecalculateResponse)
async def recalculate_risk_score(
    profile_id: uuid.UUID,
    actor: User = Depends(require_permissions("risk_assessment:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = RiskAssessmentService(db, cache)
    score = await service.recalculate(profile_id, actor.organization_id)
    return {
        "profile_id": profile_id,
        "composite_score": score.composite_score,
        "risk_level": score.risk_level,
        "factor_breakdown": score.factor_breakdown,
    }