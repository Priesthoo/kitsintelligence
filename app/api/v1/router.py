"""Aggregates every v1 sub-router into a single APIRouter mounted by main.py."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, health, organizations, users, data_source,intelligence,dashboard,alert,incident,event_correlation,risk_assessment,notification,report,knowledge_graph

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organizations.router)
api_router.include_router(data_source.router)
api_router.include_router(intelligence.router)
api_router.include_router(dashboard.router)
api_router.include_router(alert.router)
api_router.include_router(incident.router)
api_router.include_router(event_correlation.router)
api_router.include_router(risk_assessment.router)
api_router.include_router(notification.router)
api_router.include_router(report.router)
api_router.include_router(knowledge_graph.router)

