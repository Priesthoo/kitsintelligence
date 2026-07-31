"""
Knowledge Graph domain models. Entities (people, organizations, vessels,
locations, IP addresses, etc.) are nodes; Relationships are directed,
typed edges between them. This is a property graph modeled in Postgres
(rather than a dedicated graph DB) since the platform's query patterns are
mostly 1-2 hop traversals from a known starting entity, which adjacency-
list tables handle perfectly well without adding a new piece of
infrastructure.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimeStampMixin, UUIDPrimaryKeyMixin


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    VESSEL = "vessel"
    LOCATION = "location"
    IP_ADDRESS = "ip_address"
    DOMAIN = "domain"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    BANK_ACCOUNT = "bank_account"
    CVE = "cve"


class RelationshipType(StrEnum):
    ASSOCIATED_WITH = "associated_with"
    OWNS = "owns"
    EMPLOYED_BY = "employed_by"
    LOCATED_AT = "located_at"
    COMMUNICATES_WITH = "communicates_with"
    TRANSACTS_WITH = "transacts_with"
    MENTIONED_WITH = "mentioned_with"
    CONTROLS = "controls"
    MEMBER_OF = "member_of"


class Entity(Base, UUIDPrimaryKeyMixin, TimeStampMixin, SoftDeleteMixin):
    __tablename__ = "kg_entities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source_references: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    outgoing_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="source_entity", foreign_keys="EntityRelationship.source_entity_id", cascade="all, delete-orphan"
    )
    incoming_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="target_entity", foreign_keys="EntityRelationship.target_entity_id"
    )

    __table_args__ = (
        Index("ix_kg_entities_org_type", "organization_id", "entity_type"),
        Index("ix_kg_entities_normalized_name", "organization_id", "normalized_name"),
    )


class EntityRelationship(Base, UUIDPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = "kg_entity_relationships"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kg_entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kg_entities.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_references: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_entity: Mapped["Entity"] = relationship(back_populates="outgoing_relationships", foreign_keys=[source_entity_id])
    target_entity: Mapped["Entity"] = relationship(back_populates="incoming_relationships", foreign_keys=[target_entity_id])

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id", "target_entity_id", "relationship_type", name="uq_kg_relationship_triple"
        ),
        Index("ix_kg_relationships_org", "organization_id"),
        Index("ix_kg_relationships_source", "source_entity_id"),
        Index("ix_kg_relationships_target", "target_entity_id"),
    )