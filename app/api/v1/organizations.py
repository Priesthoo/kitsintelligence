"""Organization, Team, Role, and Permission endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_permissions
from app.models.identity import User
from app.schemas.identity import (
    OrganizationRead,
    OrganizationUpdate,
    PermissionRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    TeamCreate,
    TeamMemberAdd,
    TeamRead,
    TeamUpdate,
)
from app.services.organization_service import OrganizationService
from app.services.rbac_service import RBACService
from app.services.team_service import TeamService

router = APIRouter(tags=["Organizations"])


# --------------------------------------------------------------------- #
# Organization
# --------------------------------------------------------------------- #
@router.get("/organizations/current", response_model=OrganizationRead)
async def get_current_organization(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> object:
    service = OrganizationService(db)
    return await service.get(user.organization_id)


@router.patch("/organizations/current", response_model=OrganizationRead)
async def update_current_organization(
    payload: OrganizationUpdate,
    actor: User = Depends(require_permissions("organization:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = OrganizationService(db)
    return await service.update(actor.organization_id, payload, actor)


# --------------------------------------------------------------------- #
# Teams
# --------------------------------------------------------------------- #
@router.get("/teams", response_model=list[TeamRead])
async def list_teams(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    service = TeamService(db)
    teams = await service.list_for_org(user.organization_id)
    return [
        TeamRead(
            id=t.id,
            organization_id=t.organization_id,
            name=t.name,
            description=t.description,
            created_at=t.created_at,
            member_count=len(t.members),
        )
        for t in teams
    ]


@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    actor: User = Depends(require_permissions("teams:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = TeamService(db)
    team = await service.create(actor.organization_id, payload, actor)
    return TeamRead(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=0,
    )


@router.patch("/teams/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    actor: User = Depends(require_permissions("teams:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = TeamService(db)
    team = await service.update(team_id, actor.organization_id, payload)
    return TeamRead(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=len(team.members),
    )


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID,
    actor: User = Depends(require_permissions("teams:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = TeamService(db)
    await service.delete(team_id, actor.organization_id)


@router.post("/teams/{team_id}/members", response_model=TeamRead)
async def add_team_member(
    team_id: uuid.UUID,
    payload: TeamMemberAdd,
    actor: User = Depends(require_permissions("teams:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = TeamService(db)
    team = await service.add_member(team_id, actor.organization_id, payload.user_id)
    return TeamRead(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=len(team.members),
    )


@router.delete("/teams/{team_id}/members/{user_id}", response_model=TeamRead)
async def remove_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: User = Depends(require_permissions("teams:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = TeamService(db)
    team = await service.remove_member(team_id, actor.organization_id, user_id)
    return TeamRead(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=len(team.members),
    )


# --------------------------------------------------------------------- #
# RBAC: Roles & Permissions
# --------------------------------------------------------------------- #
@router.get("/permissions", response_model=list[PermissionRead])
async def list_permissions(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    service = RBACService(db)
    return await service.list_permissions()


@router.get("/roles", response_model=list[RoleRead])
async def list_roles(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list:
    service = RBACService(db)
    return await service.list_roles(user.organization_id)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    actor: User = Depends(require_permissions("roles:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = RBACService(db)
    return await service.create_role(actor.organization_id, payload, actor)


@router.patch("/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    actor: User = Depends(require_permissions("roles:write")),
    db: AsyncSession = Depends(get_db),
) -> object:
    service = RBACService(db)
    return await service.update_role(role_id, actor.organization_id, payload, actor)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    actor: User = Depends(require_permissions("roles:delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = RBACService(db)
    await service.delete_role(role_id, actor.organization_id)