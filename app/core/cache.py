"""  This is the real work and the central abstraction use dthroughout the platform for the aggregate externally, serve
    from cache pattern: background workers write hydrated data here(see app.workers.hydrated), and API routes always read
    from cache first, falling back to Postgres only for data the workers haven't hydrated yet.
    
    
    Redis_backed cache manager:
    It provides get/set/delete, JSON (de) serialization, TTL management, atomic counters , distributed locks(for scheduler mutual exclusion)
    pub/sub for WebSocket fan-out, sorted sets for leaderboards/timelines , and hash operations for structured partial update




"""

from __future__ import annotations


import asyncio
import json
from _collections_abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import orjson
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.lock import Lock
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.base import CacheError


logger = get_logger(__name__)

_pool : ConnectionPool| None = None 
#the pool is global becos it still exist outside the scope of the function 


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connection = settings.REDIS_MAX_CONNECTIONS,
            decode_responses = True
        )
    return _pool

def get_redis_client() -> Redis :
    return Redis(connection_pool=get_redis_pool())


"""The real work is here
 Heyoo CacheManager, we have work to do.

"""

class CacheManager:
    """ High level cache operation"""
    
    
    def __init(self, client : Redis | None =None) -> None:
        self._client = client or get_redis_client()
        
    """ key and values"""
    async def get(self, key:str) -> str | None :
        try:
            return await self._client.get(key)
        except RedisError as exc:
            logger.error("cache.get_failed", key=key, error = str(exc))
            raise CacheError(f"")
            
            
            
            
            
                 