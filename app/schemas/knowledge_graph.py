"""DTOs for Knowledge Graph and Entity Resolution modules."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EntityCreate(BaseModel):
    entity_type: str
    canonical_name: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    attributes_json: dict = Field(default_factory=dict)
    source_references: list[str] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    canonical_name: str | None = None
    aliases: list[str] | None = None
    attributes_json: dict | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class EntityRead(ORMBase):
    id: uuid.UUID
    entity_type: str
    canonical_name: str
    normalized_name: str
    aliases: list[str]
    latitude: float | None
    longitude: float | None
    attributes_json: dict
    confidence_score: float
    source_references: list[str]
    created_at: datetime


class RelationshipCreate(BaseModel):
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship_type: str
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = None
    source_references: list[str] = Field(default_factory=list)


class RelationshipRead(ORMBase):
    id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship_type: str
    confidence_score: float
    notes: str | None
    created_at: datetime


class GraphNode(BaseModel):
    id: uuid.UUID
    entity_type: str
    label: str
    confidence_score: float


class GraphEdge(BaseModel):
    id: uuid.UUID
    source: uuid.UUID
    target: uuid.UUID
    relationship_type: str
    confidence_score: float


class EntityGraphResponse(BaseModel):
    center_entity_id: uuid.UUID
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class EntityResolutionCandidate(BaseModel):
    entity_a_id: uuid.UUID
    entity_a_name: str
    entity_b_id: uuid.UUID
    entity_b_name: str
    similarity_score: float


class ResolveEntitiesRequest(BaseModel):
    raw_name: str = Field(min_length=1, max_length=500)
    entity_type: str


class ResolveEntitiesResponse(BaseModel):
    normalized_name: str
    exact_match: EntityRead | None
    candidates: list[EntityRead]


class MergeEntitiesRequest(BaseModel):
    primary_entity_id: uuid.UUID
    duplicate_entity_id: uuid.UUID