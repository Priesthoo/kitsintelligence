"""Team management: CRUD and membership operations."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.base import NotFoundError
from app.models.identity import Team, User
from app.repositories.identity import TeamRepository, UserRepository
from app.schemas.identity import TeamCreate, TeamUpdate
from app.repositories.audit_service import AuditService


class TeamService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.teams = TeamRepository(session)
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    async def list_for_org(self, organization_id: uuid.UUID) -> list[Team]:
        return await self.teams.list_for_org(organization_id)

    async def get(self, team_id: uuid.UUID, organization_id: uuid.UUID) -> Team:
        team = await self.teams.get(team_id)
        if team is None or team.organization_id != organization_id:
            raise NotFoundError("Team not found")
        return team

    async def create(self, organization_id: uuid.UUID, payload: TeamCreate, actor: User) -> Team:
        team = await self.teams.create(
            id=uuid.uuid4(),
            organization_id=organization_id,
            name=payload.name,
            description=payload.description,
        )
        await self.audit.record(
            action="team.create",
            resource_type="team",
            resource_id=str(team.id),
            organization_id=organization_id,
            actor_user_id=actor.id,
        )
        return team

    async def update(self, team_id: uuid.UUID, organization_id: uuid.UUID, payload: TeamUpdate) -> Team:
        team = await self.get(team_id, organization_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(team, key, value)
        await self.session.flush()
        return team

    async def delete(self, team_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        team = await self.get(team_id, organization_id)
        await self.teams.delete(team)

    async def add_member(self, team_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID) -> Team:
        team = await self.get(team_id, organization_id)
        user = await self.users.get(user_id)
        if user is None or user.organization_id != organization_id:
            raise NotFoundError("User not found in this organization")
        await self.teams.add_member(team, user)
        return team

    async def remove_member(self, team_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID) -> Team:
        team = await self.get(team_id, organization_id)
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        await self.teams.remove_member(team, user)
        return team