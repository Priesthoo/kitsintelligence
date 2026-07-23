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
            raise CacheError(f"Failed to read cache key {key}") from exc
        
    async def set(self, key:str, value : str, ttl_seconds : int | None = None) -> str :
        try :
             await self._client.set(key,value, ex = ttl_seconds or settings.CACHE_DEFAULT_TTL_SECONDS)
        except RedisError as exc:
            logger.error("cache.set_failed",key=key,error=str(exc))
            raise CacheError(f"Failed to write cache key {key}") from exc
        
    async def get_json(self,key :str) -> Any | None:
        raw = await self.get(key=key)
        if raw is None:
            return None
        try:
            return orjson.loads(raw)
        except orjson.JSONDecodeError:
            logger.warning("cache.corrupt_json", key = key, )
            return None
        
    async def delete(self, *keys : str) -> int :
        if not keys:
            return 0
        try:
            return await self._client.delete(*keys)
        except RedisError as exc:
            logger.error("cache.delete_failed", keys, error = str(exc))
            raise CacheError(f"Failed to delete cache keys")
        
    async def exists(self, key :str) -> bool :
        return bool(await self._client.exists(key))
    
    async def expire(self, key : str , ttl_seconds : int) -> None :
        await self._client.expire(key, ttl_seconds)
        
    async def ttl(self, key :str ) -> int :
        return await self._client.ttl(key)
    
    async def keys_by_pattern(self, pattern :str) -> list[str]:
        keys : list[str] = []
        async for key in self._client.scan_iter(match=pattern, count = 500):
            keys.append(key)
        return keys 
    
    async def delete_by_pattern(self, pattern : str ) -> int :
        keys = await self.keys_by_pattern(pattern=pattern)
        return await self.delete(*keys) if keys else 0
    
    
    ####Counters
    async def incr(self, key : str , amount : int=1) -> int:
        return await self._client.incrby(key,amount=amount)
    
    async def decr(self , key : str , amount : int = 1) -> int :
        return await self._client.decrby(key, amount=amount)
    
    
    ####Hashes 
    async def hset_json(self, key : str , field : str , value : Any) -> None :
        self._client.hset(key , field, orjson.dumps(value).decode())
        
    async def hget_json(self, key : str, field : str ) -> Any | None:
        raw = await self._client.hget(key, field)
        return orjson.loads(raw)  if raw else None  
    
    async def hgetall_json(self, key : str) -> dict[str, Any] :
        raw = await self._client.hgetall(key)
        return {k : orjson.loads(v) for k, v in raw.items()}
    
    async def hdel(self, key :str, *field : str) -> int :
        return await self._client.hdel(key , *field)
    
    
    ###Sorted sets
    async def zadd(self, key:str , member : str, score : float ) -> None :
        return await self._client.zadd(key , member, score)
    
    async def zrevrange(self, key : str, start : int, stop : int) -> list[str]:
        return await self._client.zrevrange(key, start,stop)
    
    async def zremrangebyrank(self, key :str, start:int, stop:int) -> None:
        await self._client.zremrangebyrank(key, start, stop)
        
    async def zcard(self, key : str) -> int:
        return await self._client.zcard(key)
    
    
    ### Pub/ Sub (WebSocket fan_out across multiples API pod replicas)
    async def publish(self, channel :str, message : dict[str, Any]) -> None:
        await self._client.publish(channel, orjson.dumps(message).decode())
        
        
    @asynccontextmanager
    async def subscribe(self, *channels : str ) -> AsyncIterator[Any] :
        pubsub = self._client.pubsub()
        await pubsub.subscribe(*channels)
        try :
            yield pubsub
        finally :
            await pubsub.unsubscribe(*channels)
            await pubsub.close()
            
            
    #Distributed lock
    def lock(self, name: str, timeout: int = 60, blocking_timeout : float = 5.0) -> Lock :
        return self._client.lock(f"lock :{name}", timeout=timeout, blocking_timeout= blocking_timeout)
    
    @asynccontextmanager
    async def acquire_lock(
        self, name: str, timeout: int = 60, blocking_timeout: float = 5.0
    ) -> AsyncIterator[bool]:
        lock_obj = self.lock(name, timeout=timeout, blocking_timeout=blocking_timeout)
        acquired = await lock_obj.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    await lock_obj.release()
                except RedisError:
                    pass

    async def ping(self) -> bool:
        try:
            return await self._client.ping()
        except RedisError:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    
    
    
    
_cache_manager : CacheManager | None = None

def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
              
            
         
            
            
            
            
            
                 