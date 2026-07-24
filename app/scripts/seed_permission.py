"""
Idempotent seed script that ensures the baseline permission catalog exists.
Run via: python -m scripts.seed_permissions
Every module in the platform gets a standard (read, write, delete) triplet;
a handful of modules get additional fine-grained actions.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.db.session import db_session_scope
from app.models.identity import Permission

configure_logging()
logger = get_logger(__name__)

RESOURCES: dict[str, list[str]] = {
    "organization": ["read", "write"],
    "users": ["read", "write", "delete"],
    "teams": ["read", "write", "delete"],
    "roles": ["read", "write", "delete"],
    "dashboard": ["read"],
    "system_status": ["read"],
    "operational_map": ["read"],
    "gis": ["read", "write"],
    "intelligence": ["read", "write"],
    "threat_intelligence": ["read", "write"],
    "risk_assessment": ["read", "write"],
    "osint": ["read", "write"],
    "socmint": ["read", "write"],
    "cyber_intelligence": ["read", "write"],
    "maritime_intelligence": ["read", "write"],
    "weather_intelligence": ["read"],
    "financial_intelligence": ["read", "write"],
    "news_intelligence": ["read"],
    "alerts": ["read", "write", "delete", "acknowledge"],
    "notifications": ["read", "write"],
    "reports": ["read", "write", "delete", "export"],
    "analytics": ["read"],
    "timeline": ["read"],
    "activity_feed": ["read"],
    "search": ["read"],
    "ai_assistant": ["read", "write"],
    "knowledge_graph": ["read", "write"],
    "entity_resolution": ["read", "write"],
    "event_correlation": ["read", "write"],
    "incidents": ["read", "write", "delete", "assign"],
    "data_sources": ["read", "write", "delete"],
    "connectors": ["read", "write", "delete", "execute"],
    "scheduler": ["read", "write"],
    "cache": ["read", "write", "delete"],
    "files": ["read", "write", "delete"],
    "audit_logs": ["read"],
    "api_keys": ["read", "write", "delete"],
    "admin": ["read", "write"],
    "settings": ["read", "write"],
    "monitoring": ["read"],
}


async def seed_permissions() -> None:
    created = 0
    async with db_session_scope() as session:
        stmt = select(Permission)
        result = await session.execute(stmt)
        existing = {(p.resource, p.action) for p in result.scalars().all()}

        for resource, actions in RESOURCES.items():
            for action in actions:
                if (resource, action) in existing:
                    continue
                session.add(
                    Permission(
                        resource=resource,
                        action=action,
                        description=f"Allows '{action}' operations on '{resource}'",
                    )
                )
                created += 1
        await session.flush()

    logger.info("seed_permissions.completed", created=created)


if __name__ == "__main__":
    asyncio.run(seed_permissions())