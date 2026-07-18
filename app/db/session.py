from __future__ import annotations

from _collections_abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)

engine = create_async_engine(
)