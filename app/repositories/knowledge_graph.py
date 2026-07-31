"""Repositories for Entity and EntityRelationship."""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models.knowledge_graph import Entity, EntityRelationship
from app.repositories.base import BaseRepository


class EntityRepository(BaseRepository[Entity]):
    model = Entity

    async def find_by_normalized_name(self, organization_id: uuid.UUID, normalized_name: str) -> Entity | None:
        stmt = select(Entity).where(
            Entity.organization_id == organization_id,
            Entity.normalized_name == normalized_name,
            Entity.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(
        self, organization_id: uuid.UUID, *, entity_type: str | None = None, offset: int = 0, limit: int = 50
    ) -> list[Entity]:
        stmt = select(Entity).where(Entity.organization_id == organization_id, Entity.is_deleted.is_(False))
        if entity_type:
            stmt = stmt.where(Entity.entity_type == entity_type)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_similar(self, organization_id: uuid.UUID, entity_type: str, limit: int = 200) -> list[Entity]:
        """Fetch candidate pool of same-type entities for similarity comparison."""
        stmt = select(Entity).where(
            Entity.organization_id == organization_id,
            Entity.entity_type == entity_type,
            Entity.is_deleted.is_(False),
        ).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class EntityRelationshipRepository(BaseRepository[EntityRelationship]):
    model = EntityRelationship

    async def list_neighbors(self, entity_id: uuid.UUID) -> list[EntityRelationship]:
        stmt = select(EntityRelationship).where(
            or_(EntityRelationship.source_entity_id == entity_id, EntityRelationship.target_entity_id == entity_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def repoint_entity_references(self, old_entity_id: uuid.UUID, new_entity_id: uuid.UUID) -> None:
        """Used during entity merge to repoint all relationships from the duplicate to the primary entity."""
        stmt = select(EntityRelationship).where(
            or_(
                EntityRelationship.source_entity_id == old_entity_id,
                EntityRelationship.target_entity_id == old_entity_id,
            )
        )
        result = await self.session.execute(stmt)
        for rel in result.scalars().all():
            if rel.source_entity_id == old_entity_id:
                rel.source_entity_id = new_entity_id
            if rel.target_entity_id == old_entity_id:
                rel.target_entity_id = new_entity_id
        await self.session.flush()