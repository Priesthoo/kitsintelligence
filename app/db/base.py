from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """ Root declarative base shared by every model in the platform"""           
    
    def as_dict(self) -> dict :
        return {c.name : getattr(self, c.name) for c in self.__table__.columns}
    
    
    
class UUIDPrimaryKeyMixin:
    id : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key= True, default= uuid.uuid4, nullable= False)
    
class TimeStampMixin:
    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= utcnow, nullable=False)
    updated_at : Mapped[datetime]  = mapped_column(DateTime(timezone = True), default=utcnow, onupdate=utcnow, nullable= False )
    
class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default= False, nullable= False)
    deleted_at : Mapped[datetime | None] =mapped_column(DateTime(timezone= True), nullable=True)
    
    def soft_delete(self) -> None :
        self.is_deletd = True
        self.deleted_at = utcnow()