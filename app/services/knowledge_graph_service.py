"""Knowledge Graph service: entity/relationship CRUD and bounded-depth graph traversal."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError, ValidationError
from app.models.knowledge_graph import Entity, EntityRelationship
from app.repositories.knowledge_graph import EntityRelationshipRepository, EntityRepository
from app.schemas.knowledge_graph import EntityCreate, EntityUpdate, RelationshipCreate
from app.utils.name_normalization import normalize_entity_name

MAX_TRAVERSAL_DEPTH = 3
MAX_NODES_PER_TRAVERSAL = 500


class KnowledgeGraphService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.entities = EntityRepository(session)
        self.relationships = EntityRelationshipRepository(session)

    async def list_entities(self, organization_id: uuid.UUID, *, entity_type: str | None = None) -> list[Entity]:
        return await self.entities.list_for_org(organization_id, entity_type=entity_type)

    async def get_entity(self, entity_id: uuid.UUID, organization_id: uuid.UUID) -> Entity:
        entity = await self.entities.get(entity_id)
        if entity is None or entity.organization_id != organization_id:
            raise NotFoundError("Entity not found")
        return entity

    async def create_entity(self, organization_id: uuid.UUID, payload: EntityCreate) -> Entity:
        normalized = normalize_entity_name(payload.canonical_name, payload.entity_type)
        return await self.entities.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            entity_type=payload.entity_type,
            canonical_name=payload.canonical_name,
            normalized_name=normalized,
            aliases=payload.aliases,
            latitude=payload.latitude,
            longitude=payload.longitude,
            attributes_json=payload.attributes_json,
            source_references=payload.source_references,
        )

    async def update_entity(self, entity_id: uuid.UUID, organization_id: uuid.UUID, payload: EntityUpdate) -> Entity:
        entity = await self.get_entity(entity_id, organization_id)
        data = payload.model_dump(exclude_unset=True)
        if "canonical_name" in data:
            entity.normalized_name = normalize_entity_name(data["canonical_name"], entity.entity_type)
        for key, value in data.items():
            setattr(entity, key, value)
        await self.session.flush()
        return entity

    async def delete_entity(self, entity_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        entity = await self.get_entity(entity_id, organization_id)
        await self.entities.delete(entity)

    async def create_relationship(self, organization_id: uuid.UUID, payload: RelationshipCreate) -> EntityRelationship:
        source = await self.get_entity(payload.source_entity_id, organization_id)
        target = await self.get_entity(payload.target_entity_id, organization_id)
        if source.id == target.id:
            raise ValidationError("An entity cannot have a relationship with itself")

        return await self.relationships.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            source_entity_id=source.id,
            target_entity_id=target.id,
            relationship_type=payload.relationship_type,
            confidence_score=payload.confidence_score,
            notes=payload.notes,
            source_references=payload.source_references,
        )

    async def delete_relationship(self, relationship_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        rel = await self.relationships.get(relationship_id)
        if rel is None or rel.organization_id != organization_id:
            raise NotFoundError("Relationship not found")
        await self.relationships.delete(rel, hard=True)

    async def get_entity_graph(self, entity_id: uuid.UUID, organization_id: uuid.UUID, *, depth: int = 2) -> dict:
        depth = min(depth, MAX_TRAVERSAL_DEPTH)
        center = await self.get_entity(entity_id, organization_id)

        visited_nodes: dict[uuid.UUID, Entity] = {center.id: center}
        visited_edges: dict[uuid.UUID, EntityRelationship] = {}
        frontier = {center.id}

        for _ in range(depth):
            next_frontier: set[uuid.UUID] = set()
            for node_id in frontier:
                edges = await self.relationships.list_neighbors(node_id)
                for edge in edges:
                    if len(visited_nodes) >= MAX_NODES_PER_TRAVERSAL:
                        break
                    visited_edges[edge.id] = edge
                    other_id = edge.target_entity_id if edge.source_entity_id == node_id else edge.source_entity_id
                    if other_id not in visited_nodes:
                        other_entity = await self.entities.get(other_id)
                        if other_entity and other_entity.organization_id == organization_id:
                            visited_nodes[other_id] = other_entity
                            next_frontier.add(other_id)
            frontier = next_frontier
            if not frontier or len(visited_nodes) >= MAX_NODES_PER_TRAVERSAL:
                break

        return {
            "center_entity_id": center.id,
            "depth": depth,
            "nodes": [
                {
                    "id": e.id,
                    "entity_type": e.entity_type,
                    "label": e.canonical_name,
                    "confidence_score": e.confidence_score,
                }
                for e in visited_nodes.values()
            ],
            "edges": [
                {
                    "id": rel.id,
                    "source": rel.source_entity_id,
                    "target": rel.target_entity_id,
                    "relationship_type": rel.relationship_type,
                    "confidence_score": rel.confidence_score,
                }
                for rel in visited_edges.values()
            ],
        }