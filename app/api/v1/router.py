"""Aggregates every v1 sub-router into a single APIRouter mounted by main.py."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, health, organizations, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organizations.router)

