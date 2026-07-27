"""
Connector Framework: the abstract base every external-data connector
implements, plus the retry/backoff/circuit-breaker wrapper that the
Hydration Engine drives.

Design: a Connector's only job is `fetch()` -> raw normalized records. It
knows nothing about scheduling, persistence, or caching -- that's the
Hydration Engine's job. This keeps each of the 89-style external
integrations a small, testable, swappable unit.
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import CONNECTOR_REQUESTS_TOTAL
from app.exceptions.base import ConnectorError

logger = get_logger(__name__)


@dataclass
class ConnectorResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    raw_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseConnector(abc.ABC):
    """Every concrete connector (weather, maritime AIS, news, threat feeds, ...) extends this."""

    key: str = "base"

    def __init__(self, config: dict[str, Any], credentials: dict[str, str] | None = None) -> None:
        self.config = config
        self.credentials = credentials or {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseConnector":
        self._client = httpx.AsyncClient(
            timeout=settings.CONNECTOR_REQUEST_TIMEOUT_SECONDS,
            headers=self.default_headers(),
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    def default_headers(self) -> dict[str, str]:
        return {"User-Agent": f"{settings.OTEL_SERVICE_NAME}/{settings.APP_VERSION}"}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError(f"Connector '{self.key}' used outside of async context manager")
        return self._client

    @abc.abstractmethod
    async def fetch(self) -> ConnectorResult:
        """Fetch and normalize data from the external source. Must be implemented by subclasses."""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Default health check hits fetch() cheaply; connectors can override for a lighter probe."""
        try:
            await self.fetch()
            return True
        except Exception:  
            return False

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.CONNECTOR_MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.CONNECTOR_RETRY_BACKOFF_SECONDS, min=1, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError, ConnectorError)),
    )
    async def fetch_with_retry(self) -> ConnectorResult:
        start = time.perf_counter()
        try:
            result = await self.fetch()
            CONNECTOR_REQUESTS_TOTAL.labels(connector=self.key, status="success").inc()
            return result
        except httpx.HTTPStatusError as exc:
            CONNECTOR_REQUESTS_TOTAL.labels(connector=self.key, status="http_error").inc()
            logger.warning(
                "connector.http_error",
                connector=self.key,
                status_code=exc.response.status_code,
                url=str(exc.request.url),
            )
            raise
        except httpx.TransportError as exc:
            CONNECTOR_REQUESTS_TOTAL.labels(connector=self.key, status="transport_error").inc()
            logger.warning("connector.transport_error", connector=self.key, error=str(exc))
            raise
        except Exception as exc:  
            CONNECTOR_REQUESTS_TOTAL.labels(connector=self.key, status="error").inc()
            logger.error("connector.unexpected_error", connector=self.key, error=str(exc))
            raise ConnectorError(f"Connector '{self.key}' failed: {exc}") from exc
        finally:
            duration = time.perf_counter() - start
            logger.debug("connector.fetch_timing", connector=self.key, duration_seconds=round(duration, 3))


class ConnectorRegistry:
    """Central registry mapping connector_key -> connector class, populated via @register_connector."""

    _registry: dict[str, type[BaseConnector]] = {}

    @classmethod
    def register(cls, key: str):  
        def _decorator(connector_cls: type[BaseConnector]) -> type[BaseConnector]:
            connector_cls.key = key
            cls._registry[key] = connector_cls
            return connector_cls

        return _decorator

    @classmethod
    def get(cls, key: str) -> type[BaseConnector]:
        if key not in cls._registry:
            raise ConnectorError(f"No connector registered under key '{key}'")
        return cls._registry[key]

    @classmethod
    def all_keys(cls) -> list[str]:
        return sorted(cls._registry.keys())


register_connector = ConnectorRegistry.register