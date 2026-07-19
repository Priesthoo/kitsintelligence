from __future__ import annotations

from _collections_abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)

engine = create_async_engine(
    settings.SQLALCHEMY_SYNC_DATABASE_URI,
    echo = settings.DB_ECHO,
    pool_pre_ping = True,
    pool_size = settings.DB_POOL_SIZE if settings.ENVIRONMENT != "test" else 5 ,
    max_overflow = settings.DB_MAX_OVERFLOW,
    pool_timeout = settings.DB_POOL_TIMEOUT,
    pool_recycle = settings.DB_POOL_RECYCLE,
    pool_class = NullPool if settings.ENVIRONMENT == "test" else None
    )


AsyncSessionFactory = async_sessionmaker(
    bind = engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False, 
    autocommit = False,
)

async  def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            

@asynccontextmanager
async def db_session_scope() -> AsyncGenerator[AsyncSession,None]:
    """" Context manager for use outside of FastAPI Dependency Injection system"""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("db_session_scope.error")
            raise
        finally:
            await session.close()
            
            
async def check_database_connection() -> bool:
    from sqlalchemy import text
    
    try:
        async with engine.connect() as conn :
            await conn.execute(text("SELECT 1"))
            
            return True
    except Exception as exc:
        logger.error("database.health_check_failed", error=str(exc))
        return False