"""
Entity Resolution service: given a raw name string, finds an exact
normalized-name match if one exists, otherwise surfaces similarity-ranked
candidates for human review, and supports merging two entity records
(repointing all relationships and unioning aliases/source_references) once
a human confirms a duplicate.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError, ValidationError
from app.models.knowledge_graph import Entity
from app.repositories.knowledge_graph import EntityRelationshipRepository, EntityRepository
from app.utils.name_normalization import name_similarity, normalize_entity_name

SIMILARITY_CANDIDATE_THRESHOLD = 0.5
MAX_CANDIDATES_RETURNED = 10


class EntityResolutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.entities = EntityRepository(session)
        self.relationships = EntityRelationshipRepository(session)

    async def resolve(self, organization_id: uuid.UUID, raw_name: str, entity_type: str) -> dict:
        normalized = normalize_entity_name(raw_name, entity_type)

        exact_match = await self.entities.find_by_normalized_name(organization_id, normalized)

        candidate_pool = await self.entities.search_similar(organization_id, entity_type)
        scored_candidates = []
        for candidate in candidate_pool:
            if exact_match and candidate.id == exact_match.id:
                continue
            score = name_similarity(normalized, candidate.normalized_name)
            if score >= SIMILARITY_CANDIDATE_THRESHOLD:
                scored_candidates.append((score, candidate))

        scored_candidates.sort(key=lambda pair: pair[0], reverse=True)
        candidates = [c for _, c in scored_candidates[:MAX_CANDIDATES_RETURNED]]

        return {
            "normalized_name": normalized,
            "exact_match": exact_match,
            "candidates": candidates,
        }

    async def merge_entities(
        self, organization_id: uuid.UUID, primary_entity_id: uuid.UUID, duplicate_entity_id: uuid.UUID
    ) -> Entity:
        if primary_entity_id == duplicate_entity_id:
            raise ValidationError("Cannot merge an entity into itself")

        primary = await self.entities.get(primary_entity_id)
        duplicate = await self.entities.get(duplicate_entity_id)

        if primary is None or primary.organization_id != organization_id:
            raise NotFoundError("Primary entity not found")
        if duplicate is None or duplicate.organization_id != organization_id:
            raise NotFoundError("Duplicate entity not found")
        if primary.entity_type != duplicate.entity_type:
            raise ValidationError("Cannot merge entities of different types")

        # Union aliases, source references; keep the higher confidence score.
        merged_aliases = sorted(set(primary.aliases) | set(duplicate.aliases) | {duplicate.canonical_name})
        merged_sources = sorted(set(primary.source_references) | set(duplicate.source_references))
        primary.aliases = merged_aliases
        primary.source_references = merged_sources
        primary.confidence_score = max(primary.confidence_score, duplicate.confidence_score)

        # Merge attributes: primary's values win on key conflicts.
        primary.attributes_json = {**duplicate.attributes_json, **primary.attributes_json}

        await self.relationships.repoint_entity_references(duplicate.id, primary.id)
        await self.entities.delete(duplicate)  # soft delete -- preserves audit trail

        await self.session.flush()
        return primary