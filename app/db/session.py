from __future__ import annotations

from _collections_abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URL,
    echo = settings.DB_ECHO,
    
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