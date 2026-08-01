"""Knowledge Graph and Entity Resolution endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permissions
from app.models.identity import User
from app.schemas.knowledge_graph import (
    EntityCreate,
    EntityGraphResponse,
    EntityRead,
    EntityUpdate,
    MergeEntitiesRequest,
    RelationshipCreate,
    RelationshipRead,
    ResolveEntitiesRequest,
    ResolveEntitiesResponse,
)
from app.services.entity_resolution_service import EntityResolutionService
from app.services.knowledge_graph_service import KnowledgeGraphService

router = APIRouter(tags=["Knowledge Graph"])


@router.get("/knowledge-graph/entities", response_model=list[EntityRead])
async def list_entities(
    entity_type: str | None = Query(default=None),
    user: User = Depends(require_permissions("knowledge_graph:read")),
    db: AsyncSession = Depends(get_db),
) -> list:
    service = KnowledgeGraphService(db)
    return await service.list_entities(user.organization_id, entity_type=entity_type)


@router.post("/knowledge-graph/entities", response_model=EntityRead, status_code=status.HTTP_201_CREATED)
async def create_entity(
    payload: EntityCreate,
    actor: User = Depends(require_permissions("knowledge_graph:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = KnowledgeGraphService(db)
    return await service.create_entity(actor.organization_id, payload)


@router.get("/knowledge-graph/entities/{entity_id}", response_model=EntityRead)
async def get_entity(
    entity_id: uuid.UUID,
    user: User = Depends(require_permissions("knowledge_graph:read")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = KnowledgeGraphService(db)
    return await service.get_entity(entity_id, user.organization_id)


@router.patch("/knowledge-graph/entities/{entity_id}", response_model=EntityRead)
async def update_entity(
    entity_id: uuid.UUID,
    payload: EntityUpdate,
    actor: User = Depends(require_permissions("knowledge_graph:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = KnowledgeGraphService(db)
    return await service.update_entity(entity_id, actor.organization_id, payload)


@router.delete("/knowledge-graph/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    entity_id: uuid.UUID,
    actor: User = Depends(require_permissions("knowledge_graph:write")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = KnowledgeGraphService(db)
    await service.delete_entity(entity_id, actor.organization_id)


@router.get("/knowledge-graph/entities/{entity_id}/graph", response_model=EntityGraphResponse)
async def get_entity_graph(
    entity_id: uuid.UUID,
    depth: int = Query(default=2, ge=1, le=3),
    user: User = Depends(require_permissions("knowledge_graph:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = KnowledgeGraphService(db)
    return await service.get_entity_graph(entity_id, user.organization_id, depth=depth)


@router.post("/knowledge-graph/relationships", response_model=RelationshipRead, status_code=status.HTTP_201_CREATED)
async def create_relationship(
    payload: RelationshipCreate,
    actor: User = Depends(require_permissions("knowledge_graph:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = KnowledgeGraphService(db)
    return await service.create_relationship(actor.organization_id, payload)


@router.delete("/knowledge-graph/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(
    relationship_id: uuid.UUID,
    actor: User = Depends(require_permissions("knowledge_graph:write")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = KnowledgeGraphService(db)
    await service.delete_relationship(relationship_id, actor.organization_id)


@router.post("/entity-resolution/resolve", response_model=ResolveEntitiesResponse)
async def resolve_entity(
    payload: ResolveEntitiesRequest,
    user: User = Depends(require_permissions("entity_resolution:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = EntityResolutionService(db)
    return await service.resolve(user.organization_id, payload.raw_name, payload.entity_type)


@router.post("/entity-resolution/merge", response_model=EntityRead)
async def merge_entities(
    payload: MergeEntitiesRequest,
    actor: User = Depends(require_permissions("entity_resolution:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = EntityResolutionService(db)
    return await service.merge_entities(actor.organization_id, payload.primary_entity_id, payload.duplicate_entity_id)