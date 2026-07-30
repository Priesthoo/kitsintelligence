"""Event Correlation endpoints: rule management, active cluster review, manual pass trigger."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_db, require_permissions
from app.core.cache import CacheManager
from app.models.identity import User
from app.repositories.base import BaseRepository
from app.models.event_correlation import CorrelationRule
from app.schemas.event_correlation import (
    CorrelationClusterRead,
    CorrelationRuleCreate,
    CorrelationRuleRead,
    CorrelationRuleUpdate,
    RunCorrelationPassResponse,
)
from app.services.correlation_service import CorrelationService

router = APIRouter(prefix="/event-correlation", tags=["Event Correlation"])


class _RuleRepo(BaseRepository[CorrelationRule]):
    model = CorrelationRule


def _cluster_to_read(cluster) -> dict:  # noqa: ANN001
    return {
        "id": cluster.id,
        "organization_id": cluster.organization_id,
        "rule_id": cluster.rule_id,
        "status": cluster.status,
        "summary": cluster.summary,
        "center_latitude": cluster.center_latitude,
        "center_longitude": cluster.center_longitude,
        "alert_count": cluster.alert_count,
        "max_severity": cluster.max_severity,
        "escalated_incident_id": cluster.escalated_incident_id,
        "created_at": cluster.created_at,
        "member_alert_ids": [m.alert_id for m in cluster.members],
    }


@router.get("/rules", response_model=list[CorrelationRuleRead])
async def list_rules(
    user: User = Depends(require_permissions("event_correlation:read")), db: AsyncSession = Depends(get_db)
) -> list:
    service = CorrelationService(db, None)  # cache unused for pure rule listing
    return await service.rules.list_active_for_org(user.organization_id)


@router.post("/rules", response_model=CorrelationRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: CorrelationRuleCreate,
    actor: User = Depends(require_permissions("event_correlation:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    repo = _RuleRepo(db)
    return await repo.create(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        name=payload.name,
        rule_type=payload.rule_type,
        parameters_json=payload.parameters_json,
        auto_escalate_threshold=payload.auto_escalate_threshold,
        auto_escalate_severity=payload.auto_escalate_severity,
        is_active=True,
    )


@router.patch("/rules/{rule_id}", response_model=CorrelationRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    payload: CorrelationRuleUpdate,
    actor: User = Depends(require_permissions("event_correlation:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    from app.exceptions.base import NotFoundError

    repo = _RuleRepo(db)
    rule = await repo.get(rule_id)
    if rule is None or (rule.organization_id and rule.organization_id != actor.organization_id):
        raise NotFoundError("Correlation rule not found")
    data = payload.model_dump(exclude_unset=True)
    return await repo.update(rule, **data)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    actor: User = Depends(require_permissions("event_correlation:write")),
    db: AsyncSession = Depends(get_db),
) -> None:
    from app.exceptions.base import NotFoundError

    repo = _RuleRepo(db)
    rule = await repo.get(rule_id)
    if rule is None or (rule.organization_id and rule.organization_id != actor.organization_id):
        raise NotFoundError("Correlation rule not found")
    await repo.delete(rule, hard=True)


@router.get("/clusters", response_model=list[CorrelationClusterRead])
async def list_active_clusters(
    user: User = Depends(require_permissions("event_correlation:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> list:
    service = CorrelationService(db, cache)
    clusters = await service.list_active_clusters(user.organization_id)
    return [_cluster_to_read(c) for c in clusters]


@router.get("/clusters/{cluster_id}", response_model=CorrelationClusterRead)
async def get_cluster(
    cluster_id: uuid.UUID,
    user: User = Depends(require_permissions("event_correlation:read")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = CorrelationService(db, cache)
    cluster = await service.get_cluster(cluster_id, user.organization_id)
    return _cluster_to_read(cluster)


@router.post("/clusters/{cluster_id}/dismiss", response_model=CorrelationClusterRead)
async def dismiss_cluster(
    cluster_id: uuid.UUID,
    user: User = Depends(require_permissions("event_correlation:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = CorrelationService(db, cache)
    cluster = await service.dismiss_cluster(cluster_id, user.organization_id)
    return _cluster_to_read(cluster)


@router.post("/run-now", response_model=RunCorrelationPassResponse)
async def run_correlation_pass_now(
    actor: User = Depends(require_permissions("event_correlation:write")),
    db: AsyncSession = Depends(get_db),
    cache: CacheManager = Depends(get_cache),
) -> dict:
    service = CorrelationService(db, cache)
    return await service.run_correlation_pass(actor.organization_id)