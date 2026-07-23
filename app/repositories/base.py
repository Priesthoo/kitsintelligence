"""
Generic repository base class implementing the repository pattern over
SQLAlchemy's async session. Concrete repositories subclass this to add
entity-specific queries; the base handles the common CRUD + pagination +
soft-delete plumbing so it is not duplicated across every module.
"""
from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: uuid.UUID) -> ModelType | None:
        result = await self.session.get(self.model, id_)
        if result is not None and getattr(result, "is_deleted", False):
            return None
        return result

    async def get_or_none(self, **filters: Any) -> ModelType | None:
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _apply_soft_delete_filter(self, stmt: Select) -> Select:
        if hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        order_by: Any = None,
        **filters: Any,
    ) -> list[ModelType]:
        stmt = select(self.model).filter_by(**filters)
        stmt = self._apply_soft_delete_filter(stmt)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        stmt = self._apply_soft_delete_filter(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, **kwargs: Any) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelType, **kwargs: Any) -> ModelType:
        for key, value in kwargs.items():
            if value is not None or key in kwargs:
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelType, *, hard: bool = False) -> None:
        if hard or not hasattr(instance, "soft_delete"):
            await self.session.delete(instance)
        else:
            instance.soft_delete()
        await self.session.flush()

    async def paginate(
        self, *, page: int = 1, page_size: int = 50, order_by: Any = None, **filters: Any
    ) -> tuple[list[ModelType], int]:
        offset = (page - 1) * page_size
        items = await self.list(offset=offset, limit=page_size, order_by=order_by, **filters)
        total = await self.count(**filters)
        return items, total